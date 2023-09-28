from datetime import timedelta
from models.graph import Graph
from models.handing import FlightData
from models.utils import AirportParkingScene, AirfieldStoppages
from models.utils import GraphNode, AirportSlot, SlotItem, AdjTabItem, AdjustItem
from models.cplex_solver import MultiFlowModel


def list_reverse(nums):
    return list(map(list, zip(*nums)))


class MultiFlowProblem(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_list = self.flight_data.graph_node_list  # 可以用到的时候再复制
        self.airport_parking_scene = AirportParkingScene()
        self.airport_parking_map = dict()
        self.airport_parking_capacity = list()
        self.adjacency_tabl = dict()  # 储存邻接表
        self.node2num_map = dict()  # 储存可执行航班到在邻接矩阵中的行的指标
        self.num2node_map = dict()
        self.edge_ls = dict()  # 储存可执行边
        self.edge2num_map = dict()  # 储存可执行边在邻接矩阵中的列的指标
        self.ass_matrix = list()  # 储存邻接矩阵
        self.edge_cost_list = list()  # 储存边的执行花费
        self.node_attr_list = list()  # 存储node的出入度情况
        self.cancel_ct_list = list()  # 储存取消约束
        self.node_cancel_cost = list()  # node取消成本
        self.mutex_graph_node_edge_list = dict()
        self.exceeded_slots = list()  # 储存落入数量超过容量的slot信息
        self.exceeded_slots_capacity = list()  # 储存落入数量超过容量的slot的容量
        self.exceeded_slots_map = dict()  # 储存落入数据超过容量的slot的标号

        self.optimal = None
        self.solution_x = list()
        self.solution_y = list()
        self.all_edge_string = list()
        self.graph_node_string = set()
        self.fids_string = list()

        flight_cancel_cost = []
        for node_num, graph_node in self.flight_data.graph_node_list.items():
            graph_node: GraphNode
            if node_num >= 0:
                flight_cancel_cost.append(graph_node.flight_info["para"] * 1200 + graph_node.flight_info["pn"] * 4)
        self.flight_cancel_cost = flight_cancel_cost
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
        self.node_attr_list = [0]*node_cnt
        self.cancel_ct_list = [0]*node_cnt
        self.node_cancel_cost = [0]*node_cnt
        # 再遍历所有边，并做好map
        edge_cnt = 0
        for v in self.graph_node_list.values():
            for ai in v.adjust_list.values():
                edge_airm = (v.key, ai.adjust_time)
                edge_airm_num = self.node2num_map[edge_airm]
                if -aircraft_num <= v.key < 0:
                    self.node_attr_list[edge_airm_num] = 1
                elif v.key < -aircraft_num:
                    self.node_attr_list[edge_airm_num] = -1
                else:
                    self.cancel_ct_list[edge_airm_num] = 2
                    self.node_cancel_cost[edge_airm_num] = self.flight_cancel_cost[v.key]
                for from_graph_num, from_adjust_time, cost in ai.pre:
                    edge_from = (from_graph_num, from_adjust_time)
                    edge_from_num = self.node2num_map[edge_from]
                    self.edge2num_map[(edge_from_num, edge_airm_num)] = edge_cnt
                    self.edge_ls[edge_cnt] = (edge_from_num, edge_airm_num)
                    column = [0] * node_cnt
                    column[edge_from_num] = 1
                    column[edge_airm_num] = -1
                    self.ass_matrix.append(column)
                    self.edge_cost_list.append(cost)
                    edge_cnt += 1
            # 有多个后继的增加互斥约束
            if len(v.adjust_list) >= 2:
                for ai in v.adjust_list.values():
                    edge_airm = (v.key, ai.adjust_time)
                    edge_airm_num = self.node2num_map[edge_airm]
                    if v.key in self.mutex_graph_node_edge_list.keys():
                        self.mutex_graph_node_edge_list[v.key].append(edge_airm_num)
                    else:
                        self.mutex_graph_node_edge_list[v.key] = [edge_airm_num]
        self.ass_matrix = list_reverse(self.ass_matrix)

    def run(self):
        self.generate_association_matrix(self.flight_data.aircraft_volume)
        mfp_solver = MultiFlowModel(self.ass_matrix, self.node_attr_list, self.edge_cost_list, self.node_cancel_cost)
        # mfp_solver.add_mutex_constraint(self.mutex_graph_node_edge_list)
        mfp_solver.print_info()
        mfp_solver.solve()
        print("Zhang Chor is a good name!")
        self.optimal = mfp_solver.optimal
        self.solution_x = mfp_solver.solution_x
        self.solution_y = mfp_solver.solution_y
        if self.is_solution_int:
            print(mfp_solver.optimal)
            print(mfp_solver.solution_x)
            print(mfp_solver.solution_y)
            self.print_solution()
        else:
            print("NOT INT SOLUTION")

    @property
    def is_solution_int(self) -> bool:
        for i in self.solution_x:
            if i != int(i):
                return False
        return True

    def print_solution(self):
        self.all_edge_string = list()
        for i in range(len(self.solution_x)):
            if self.solution_x[i]:
                self.all_edge_string.append(self.edge_ls[i])
        for edge_from, edge_airm in self.all_edge_string:
            if edge_from >= 0:
                self.graph_node_string.add(self.num2node_map[edge_from])
            if edge_airm >= 0:
                self.graph_node_string.add(self.num2node_map[edge_airm])
        print(*self.graph_node_string)



