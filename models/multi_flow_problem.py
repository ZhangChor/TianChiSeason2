from datetime import datetime, timedelta
from time import time as current_time
from docplex.mp.model import Model
from scipy.sparse import csr_matrix, csc_matrix, lil_matrix

from models.handing import FlightData
from models.graph import Graph
from models.utils import AirportParkingScene, GraphNode


class MultiFlowModel(object):
    def __init__(self, ass_matrix: csr_matrix, flow_ct: list, edge_cost: list,
                 mutex_matrix: dict, cancel_cost: list, flight_num: int):
        self.node_num = len(flow_ct)  # number of node
        self.edge_num = len(edge_cost)  # number of edge
        self.cancel_num = len(cancel_cost)  # number of flight
        self._var_x_name_list = [f'e{j}' for j in range(self.edge_num)]
        self._var_y_name_list = [f'n{i}' for i in range(self.cancel_num)]
        self.mfp = Model(name="multi flow model problem")

        self.var_x_list = self.mfp.binary_var_list(self._var_x_name_list, name='x')
        self.var_y_list = self.mfp.binary_var_list(self._var_y_name_list, name='y')
        # 流平衡约束
        for i in range(self.node_num):
            row = ass_matrix[i]
            zeros, cols = row.nonzero()
            self.mfp.add_constraint(
                self.mfp.sum(ass_matrix[i, j]*self.var_x_list[j] for j in cols) == flow_ct[i], ctname=f'node{i}')

        # 航班取消成本
        for i, mutex_list in mutex_matrix.items():
            self.mfp.add_constraint(self.mfp.sum(self.var_x_list[j] for j in mutex_list) + self.var_y_list[i] == 1,
                                    ctname=f'cancel_node{i}')
        self.mfp.minimize(self.mfp.sum(edge_cost[j] * self.var_x_list[j] for j in range(self.edge_num)) +
                          self.mfp.sum(cancel_cost[j] * self.var_y_list[j] for j in range(self.cancel_num)))
        self.result = None

    def add_mutex_constraint(self, mutex_graph_node_edges: dict):
        # 顶点互斥约束
        k = 0
        for graph_node_num, edges in mutex_graph_node_edges.items():
            node_ct = [0] * self.edge_num
            for i in edges:
                node_ct[i] = 1
            self.mfp.add_constraint(self.mfp.sum(node_ct[j] * self.var_x_list[j] for j in range(self.edge_num)) <= 1,
                                    ctname=f'mut_flight{k}')
            k += 1

    def add_fix_int_var(self, solution_x: list):
        for i in range(len(solution_x)):
            if solution_x[i] == 1:
                self.mfp.add_constraint(self.var_x_list[i] == 1)

    def print_info(self):
        for j in range(self.node_num):
            print(self.mfp.get_constraint_by_name('node%s' % j))
        for j in range(self.cancel_num):
            print(self.mfp.get_constraint_by_name('cancel_node%s' % j))

        # 输出目标函数
        print("Objective:")
        print(self.mfp.get_objective_expr())
        self.mfp.print_information()  # 输出模型信息

    def solve(self):
        self.result = self.mfp.solve()
        if not self.result:
            self.result = self.mfp.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution_x(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_x_name_list]

    @property
    def solution_y(self) -> list:
        return [self.result.get_value('y_' + s) for s in self._var_y_name_list]

    @property
    def optimal(self) -> float:
        return self.mfp.objective_value


class MultiFlowProblem(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_list = self.flight_data.graph_node_list  # 可以用到的时候再复制
        self.airport_parking_scene = AirportParkingScene()
        self.airport_parking_map = dict()
        self.airport_parking_capacity = list()
        self.airport_parking_edges = dict()
        self.adjacency_tabl = dict()  # 储存邻接表
        self.node2num_map = dict()  # 储存可执行航班到在邻接矩阵中的行的指标
        self.num2node_map = dict()
        self.edge_ls = dict()  # 储存可执行边
        self.edge2num_map = dict()  # 储存可执行边在邻接矩阵中的列的指标
        self.ass_matrix = None  # 储存邻接矩阵
        self.edge_cost_list = list()  # 储存边的执行花费
        self.node_attr_list = list()  # 存储node的出入度情况
        self.cancel_ct_list = list()  # 储存取消约束
        self.node_cancel_cost = list()  # node取消成本
        self.cancel_graph_node = list()  # 标记需要取消的graph node

        self.mutex_graph_node_edge_list = dict()
        self.exceeded_slots = list()  # 储存落入数量超过容量的slot信息
        self.exceeded_slots_capacity = list()  # 储存落入数量超过容量的slot的容量
        self.exceeded_slots_map = dict()  # 储存落入数据超过容量的slot的标号

        self.optimal = None
        self.solution_x = list()
        self.solution_y = list()
        self.all_edge_string = list()
        self.graph_node_string = set()
        self.edge_route = list()
        self.solution_route = dict()
        self.fids_string = dict()
        self.output = OutPutInfo()

        flight_cancel_cost = []
        for node_num, graph_node in self.flight_data.graph_node_list.items():
            graph_node: GraphNode
            if node_num >= 0:
                flight_cancel_cost.append(graph_node.flight_info["para"] * 1200 + graph_node.flight_info["pn"] * 4)
        self.flight_cancel_cost = flight_cancel_cost
        self.mutex_flight_list = {i: set() for i in range(len(self.flight_cancel_cost))}  # 航班互斥约束
        self.slot_used = list()  # 储存每条路径的slot使用情况
        self.parking_used = list()  # 储存每条路径的停机使用情况

    def add_airport_parking(self, airport_parking_constraint_list: list):
        airfield_stoppage_num = 0
        for item in airport_parking_constraint_list:
            airport_num, start_time, end_time, capacity = item
            self.airport_parking_scene[airport_num] = AirfieldStoppages(airport_num, start_time, end_time, capacity)
            self.airport_parking_map[airport_num] = airfield_stoppage_num
            self.airport_parking_capacity.append(capacity)
            airfield_stoppage_num += 1
        self.airport_parking_edges = {airport_num: list() for airport_num in self.airport_parking_map.keys()}

    def generate_dep_arr_slot_matrix(self):
        # 遍历SoltScene，寻找落入数量大于容量的slot，进行编号
        slot_scene = self.flight_data.slot_scene
        exceeded_slots_num = 0
        for airport_num, airport_slot_ls in slot_scene.scene_list.items():
            airport_slot: AirportSlot = airport_slot_ls[0]
            for sl in airport_slot.takeoff_slot.slot_ls:
                sl: SlotItem
                if len(sl.fall_in) > sl.capacity:
                    slot_mark = (airport_num, 'takeoff', sl.start_time)
                    self.exceeded_slots.append(slot_mark)
                    self.exceeded_slots_capacity.append(sl.capacity)
                    self.exceeded_slots_map[slot_mark] = exceeded_slots_num
                    exceeded_slots_num += 1
            for sl in airport_slot.landing_slot.slot_ls:
                sl: SlotItem
                if len(sl.fall_in) > sl.capacity:
                    slot_mark = (airport_num, 'landing', sl.start_time)
                    self.exceeded_slots.append(slot_mark)
                    self.exceeded_slots_capacity.append(sl.capacity)
                    self.exceeded_slots_map[slot_mark] = exceeded_slots_num
                    exceeded_slots_num += 1

    def generate_association_matrix(self, aircraft_num: int):
        """
        遍历图中所有边，并生成相关矩阵
        :return:
        """
        # 先遍历一遍所有adjust item，并做好map
        node_cnt = 0
        for v in self.graph_node_list.values():
            for ai in v.adjust_list.values():
                self.node2num_map[(v.key, ai.adjust_time)] = node_cnt
                self.num2node_map[node_cnt] = (v.key, ai.adjust_time)
                node_cnt += 1
        self.node_attr_list = [0] * node_cnt
        # 再遍历所有边，并做好map
        edge_cnt = 0
        row, col, val = list(), list(), list()
        for v in self.graph_node_list.values():
            v: GraphNode
            for ai in v.adjust_list.values():
                ai: AdjustItem
                edge_airm = (v.key, ai.adjust_time)
                edge_airm_num = self.node2num_map[edge_airm]
                if -aircraft_num <= v.key < 0:  # departure node
                    self.node_attr_list[edge_airm_num] = 1
                elif v.key < -aircraft_num:  # arrival node
                    airm_airport_graph_node = self.graph_node_list[v.key]
                    airm_airport = airm_airport_graph_node.flight_info['ap']
                    aircraft_ct = sum(self.flight_data.airport_list[airm_airport].terminal_ctp)
                    self.node_attr_list[edge_airm_num] = -aircraft_ct
                for from_graph_num, from_adjust_time, cost in ai.pre:
                    edge_from = (from_graph_num, from_adjust_time)
                    edge_from_num = self.node2num_map[edge_from]
                    self.edge2num_map[(edge_from_num, edge_airm_num)] = edge_cnt
                    self.edge_ls[edge_cnt] = (edge_from_num, edge_airm_num)
                    row.append(edge_from_num)
                    col.append(edge_cnt)
                    val.append(1)
                    row.append(edge_airm_num)
                    col.append(edge_cnt)
                    val.append(-1)
                    if from_graph_num >= 0:
                        self.mutex_flight_list[from_graph_num].add(edge_cnt)
                    self.edge_cost_list.append(cost)
                    edge_cnt += 1
        self.ass_matrix = csr_matrix((val, (row, col)), shape=(node_cnt, edge_cnt))
        # 有多个后继的增加互斥约束
        for v in self.graph_node_list.values():
            v: GraphNode
            if len(v.adjust_list) >= 2:
                for ai in v.adjust_list.values():
                    node_from = (v.key, ai.adjust_time)
                    node_from_num = self.node2num_map[node_from]
                    in_parking_scene = v.flight_info['ap'] in self.airport_parking_map.keys()
                    for node_airm in ai.suc:
                        node_airm_num = self.node2num_map[node_airm]
                        edge = (node_from_num, node_airm_num)
                        edge_num = self.edge2num_map[edge]
                        # 判断是否停在了停机受限机场
                        suc_node_num, suc_adjust_time = node_airm
                        suc_dpt = self.graph_node_list[suc_node_num].adjust_list[suc_adjust_time].departure_time
                        if in_parking_scene:
                            parking_scene: AirfieldStoppages = self.airport_parking_scene[v.flight_info['ap']]
                            if v.flight_info['avt'] <= parking_scene.start_time and parking_scene.end_time <= suc_dpt:
                                self.airport_parking_edges[v.flight_info['ap']].append(edge_num)

    def run(self, relation=True):
        from time import time as current_time
        t10 = current_time()
        self.generate_association_matrix(self.flight_data.aircraft_volume)
        mfp_solver = MultiFlowModel(self.ass_matrix, self.node_attr_list, self.edge_cost_list,
                                      self.mutex_flight_list, self.flight_cancel_cost)
        mfp_solver.add_mutex_constraint(self.mutex_graph_node_edge_list)
        # mfp_solver.print_info()
        t11 = current_time()
        print("构造问题时间：", t11 - t10)
        mfp_solver.solve()
        self.optimal = mfp_solver.optimal
        self.solution_x = mfp_solver.solution_x
        self.solution_y = mfp_solver.solution_y
        t12 = current_time()
        self.print_solution(t12 - t11)
        if not self.is_solution_int:
            print("SOLUTION IS NOT INTEGER.")
            pass
        else:
            print("SOLVE DONE.")

    @property
    def is_solution_int(self) -> bool:
        for i in self.solution_x:
            if i != int(i):
                return False
        for i in self.solution_y:
            if i not in (0, 1):
                return False
        return True

if __name__ == '__main__':
    workspace_path = r"D:/workspace/TianChiSeason2"
    # workspace_path = r"/home/zc/TianChiSeason2"
    min_turn_time = timedelta(minutes=50)
    duration_start = datetime(year=2017, month=5, day=6, hour=6)
    duration_end = datetime(year=2017, month=5, day=9, hour=0)

    max_lead_time = timedelta(hours=6)
    max_domestic_delay = timedelta(hours=24)
    max_foreign_delay = timedelta(hours=36)

    split_time = timedelta(minutes=60)
    slot_capacity = 24

    flight_data = FlightData(min_turn_time, duration_start, duration_end,
                             max_lead_time, max_domestic_delay, max_foreign_delay,
                             split_time, slot_capacity, workspace_path)
    AIRCRAFT_NUM = 5
    typhoon_list = [(49, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (50, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (61, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17))]
    flight_data.add_typhoon(typhoon_list)
    start_time = datetime(year=2017, month=5, day=6, hour=0)
    end_time = datetime(year=2017, month=5, day=8, hour=0)
    flight_data.selection_data(AIRCRAFT_NUM)
    mega_graph = Graph(flight_data)
    close_list = [(5, timedelta(hours=0, minutes=1), timedelta(hours=6, minutes=30),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (6, timedelta(hours=0, minutes=0), timedelta(hours=6, minutes=0),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (6, timedelta(hours=23, minutes=0), timedelta(hours=23, minutes=59),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (22, timedelta(hours=11, minutes=15), timedelta(hours=11, minutes=45),
                   datetime(year=2017, month=5, day=4), datetime(year=2017, month=5, day=7)),
                  (49, timedelta(hours=0, minutes=10), timedelta(hours=6, minutes=10),
                   datetime(year=2017, month=4, day=28), datetime(year=2017, month=6, day=1)),
                  (76, timedelta(hours=1, minutes=0), timedelta(hours=7, minutes=0),
                   datetime(year=2017, month=4, day=28), datetime(year=2017, month=7, day=9))]
    mega_graph.add_close(close_list)
    t0 = current_time()
    mega_graph.build_graph_v2()
    mfp = MultiFlowProblem(mega_graph)