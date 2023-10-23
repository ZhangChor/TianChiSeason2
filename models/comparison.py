import csv
from datetime import timedelta, datetime
from scipy.sparse import csr_matrix
from models.graph import Graph
from models.handing import FlightData
from models.utils import AirportParkingScene, AirfieldStoppages
from models.utils import GraphNode, AirportSlot, SlotItem, AdjustItem, OutPutInfo
from models.utils import dot_sum, timedelta_minutes
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
        # self.node_cancel_cost = list()  # node取消成本

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
                                    self.mutex_flight_list, self.flight_cancel_cost, relation=relation)
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
            # mfp_solver = MultiFlowModel(self.ass_matrix, self.node_attr_list, self.edge_cost_list,
            #                             self.node_cancel_cost, relation=False)
            # mfp_solver.add_mutex_constraint(self.mutex_graph_node_edge_list)
            # mfp_solver.add_fix_int_var(self.solution_x)
            # mfp_solver.solve()
            # self.optimal = mfp_solver.optimal
            # self.solution_x = mfp_solver.solution_x
            # self.solution_y = mfp_solver.solution_y
            # t2 = current_time()
            # self.print_solution(t2 - t1, mode='a')
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

    def print_solution(self, running_time: float, mode='w'):
        self.all_edge_string = list()
        for i in range(len(self.solution_x)):
            if self.solution_x[i]:
                self.all_edge_string.append(self.edge_ls[i])
        for edge_from, edge_airm in self.all_edge_string:
            if edge_from >= 0:
                self.graph_node_string.add(self.num2node_map[edge_from])
            if edge_airm >= 0:
                self.graph_node_string.add(self.num2node_map[edge_airm])
        # 融合路径
        string_set = list()
        for i in range(len(self.all_edge_string)):
            from_node, airm_node = self.all_edge_string[i]
            merge, attach = -1, -1
            for j in range(len(string_set)):
                exist_string = string_set[j]
                if airm_node == exist_string[0]:
                    merge = j
                    exist_string.insert(0, from_node)
                if from_node == exist_string[-1]:
                    attach = j
                    exist_string.append(airm_node)
            if merge >= 0 and attach >= 0:
                front_string = string_set[attach]
                back_string = string_set[merge]
                front_string.pop(-1)
                back_string.pop(0)
                new_string_set = [[*front_string, *back_string]]
                for j in range(len(string_set)):
                    if j != merge and j != attach:
                        new_string_set.append(string_set[j])
                string_set = new_string_set
            elif merge < 0 and attach < 0:
                string_set.append([from_node, airm_node])
        self.edge_route = string_set

        for node_route_nums in self.edge_route:
            first_node_num = node_route_nums[0]
            first_graph_node_num, first_adjust_time = self.num2node_map[first_node_num]
            graph_node_string = [self.num2node_map[nn] for nn in node_route_nums]
            self.solution_route[-first_graph_node_num] = graph_node_string
        # 计算成本，统计解的信息
        change_cost, execution_cost, cancel_cost = 0, 0, 0
        effect_flight = 0
        cancel_graph_node = [1] * len(self.flight_cancel_cost)
        zero_time = timedelta(minutes=0)
        pas_15_time = timedelta(minutes=15)
        pas_30_time = timedelta(minutes=30)
        net_15_time = zero_time - pas_15_time
        net_30_time = zero_time - pas_30_time
        for cid, graph_node_string in self.solution_route.items():
            tp = self.graph_node_list[-cid].flight_info["tp"]
            for graph_node_num, adjust_time in graph_node_string:
                graph_node = self.graph_node_list[graph_node_num]
                flight_info = graph_node.flight_info
                adjust_item: AdjustItem = graph_node.adjust_list[adjust_time]
                if graph_node_num >= 0:
                    cancel_graph_node[graph_node_num] = 0

                    self.output.performed_flights += len(flight_info["fids"])
                    if flight_info["tmk"]:
                        effect_flight += len(flight_info["fids"])
                    if adjust_time > zero_time:
                        self.output.del_flights += 1
                        delay_minutes = timedelta_minutes(adjust_time)
                        self.output.total_del_minutes += delay_minutes
                        self.output.passenger_delay_nums += flight_info["pn"]
                        self.output.passenger_delay_minutes += flight_info["pn"] * delay_minutes
                        self.output.seat_remains += flight_info["sn"] - flight_info["pn"]
                        if adjust_time > pas_15_time:
                            self.output.del_15m_flights += 1
                            if adjust_time > pas_30_time:
                                self.output.del_30m_flights += 1
                    if adjust_time < zero_time:
                        self.output.adv_flights += 1
                        self.output.total_adv_minutes -= timedelta_minutes(adjust_time)
                        if adjust_time < net_15_time:
                            self.output.adv_15m_flights += 1
                            if adjust_time < net_30_time:
                                self.output.adv_30m_flights += 1
                    if flight_info["tp"] != tp:
                        self.output.aircraft_type_conversion += 1
                    if flight_info["attr"] == "straighten":
                        self.output.straighten_flights += 1
                    if flight_info["attr"] == "through":
                        self.output.passenger_cancellation += flight_info["tpn"]
                    if flight_info["cid"] != cid:
                        self.output.swap_flights += 1
                    if adjust_item.departure_time.day > flight_info["dpt"].day:
                        self.output.make_up_flights += 1

                    # if graph_node.flight_info["cid"] != cid:
                    #     if graph_node.adjust_list[adjust_time].departure_time <= datetime(2017, 5, 6, 16):
                    #         change_cost += 15
                    #     else:
                    #         change_cost += 5
        cancel_cost += dot_sum(cancel_graph_node, self.flight_cancel_cost)
        execution_cost += dot_sum(self.solution_x, self.edge_cost_list)

        for i in range(len(cancel_graph_node)):
            if cancel_graph_node[i] == 1:
                graph_node: GraphNode = self.graph_node_list[i]
                flight_info = graph_node.flight_info
                self.output.flight_cancellation += len(flight_info["fids"])
                self.output.passenger_cancellation += flight_info["pn"]
                self.output.seat_remains += flight_info["sn"]
        self.output.error_rate = (
                                             self.output.del_15m_flights + self.output.adv_15m_flights) / self.output.performed_flights if self.output.performed_flights else 0
        self.output.avg_del_minutes = self.output.total_del_minutes / self.output.del_flights if self.output.del_flights else 0
        self.output.avg_adv_minutes = self.output.total_adv_minutes / self.output.adv_flights if self.output.adv_flights else 0

        total_cost = cancel_cost + execution_cost
        print(f"执行成本：{execution_cost}")
        print(f"受影响航班：{effect_flight}")
        print(f"取消成本：{cancel_cost}")
        print(f"总成本：{total_cost}")
        print(f"求解时间：{timedelta(seconds=running_time)}")
        file_name = self.flight_data.workspace_path + r"/solution"
        result_file_name = file_name + "/cid" + str(self.flight_data.aircraft_volume) + "result.txt"
        with open(result_file_name, mode) as txtfile:
            txtfile.write(f"Aircraft volume={self.flight_data.aircraft_volume}" + '\n')
            txtfile.write(f"执行成本：{execution_cost}" + '\n')
            txtfile.write(f"受影响航班：{effect_flight}" + '\n')
            txtfile.write(f"取消成本：{cancel_cost}" + '\n')
            txtfile.write(f"总成本：{total_cost}" + '\n')
            txtfile.write(f"求解时间：{timedelta(seconds=running_time)}" + '\n')

        route_info_file_name = file_name + "/cid" + str(self.flight_data.aircraft_volume) + "route_info.csv"
        self.output.scores = cancel_cost + execution_cost
        self.output.running_time = running_time
        route_info = self.output.data_picked()
        header_field_name = route_info.keys()  # 使用字典的keys作为列名
        with open(route_info_file_name, mode='w', newline='') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=header_field_name)
            writer.writeheader()
            writer.writerow(route_info)
