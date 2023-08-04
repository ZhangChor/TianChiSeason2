from pickle import dumps, loads
from datetime import timedelta

from models.graph import Graph
from models.handing import FlightData
from models.utils import timedelta_minutes
from models.utils import GraphNode, AdjustItem, AdjTabItem, AirportSlot, SlotItem
from models.utils import AirportParkingScene, AirfieldStoppages
from models.cplex_solver import ShortestPath


def deep_copy(data):
    return loads(dumps(data))  # 代替copy.deepcopy


class ColumnGeneration(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_list = self.flight_data.graph_node_list  # 可以用到的时候再复制
        self.airport_parking_scene = AirportParkingScene()
        self.aircraft_top_order = dict()  # 每架飞机的可执行航班的拓扑排序都不一定一样
        self.adjacency_table_list = dict()  # 储存每架飞机的邻接表
        self.node2num_map_list = dict()  # 储存每架飞机可执行航班到在邻接矩阵中的行的指标
        self.edge_ls_list = dict()  # 储存每架飞机可执行边
        self.edge2num_map_list = dict()  # 储存每架飞机可执行边在邻接矩阵中的列的指标

        self.ass_matrix_list = dict()  # 储存每架飞机的邻接矩阵
        self.edge_cost_list = dict()  # 储存每架飞机边的执行花费
        self.node_attr_list = dict()  # 存储每架飞机的node的出入度情况
        self.graph_node_index_list = dict()

        self.exceeded_slots = list()  # 储存落入数量超过容量的slot信息
        self.exceeded_slots_capacity = list()  # 储存落入数量超过容量的slot的容量
        self.exceeded_slots_map = dict()  # 储存落入数据超过容量的slot的标号

        self.terminal_airport_list = list()  # 储存在恢复期结束时，需要有不同数量的相应类型的飞机
        self.terminal_airport_needs_list = list()  # 储存在恢复期结束时，所需相应类型的飞机的数量
        self.terminal_airport_index_map = dict()  # 存储终点机场的编号
        # 设置对偶值
        self.aircraft_dual = [0] * len(self.flight_data.aircraft_list)
        flight_cancel_cost = []
        for node_num, graph_node in self.flight_data.graph_node_list.items():
            graph_node: GraphNode
            if node_num >= 0:
                flight_cancel_cost.append(graph_node.flight_info["para"] * 1200)
        self.flight_cancel_cost = flight_cancel_cost
        self.flight_dual = [-x for x in flight_cancel_cost]  # 航班取消成本为航班对偶值的上界
        # self.flight_dual = [0] * len(flight_cancel_cost)  # 初始航班对偶值设为0
        self.slot_dual = None
        self.terminal_airport_dual = None
        self.airfield_stoppage_dual = None

        self.route = list()  # 储存所有路径集
        self.route_execution_costs = list()  # 记录每条路径的执行成本
        self.route_reduce_costs = list()  # 记录每条路径的reduce cost
        self.aircraft_route_nums = [0] * len(self.flight_data.aircraft_list)  # 记录每架飞机现有路径个数
        self.solution_x = None
        self.solution_y = None
        self.solution_z = None
        self.optimal_value_list = list()
        self.iter_num = 0

    def add_airport_parking(self, airport_parking_constraint_list: list):
        for item in airport_parking_constraint_list:
            airport_num, start_time, end_time, capacity = item
            self.airport_parking_scene[airport_num] = AirfieldStoppages(airport_num, start_time, end_time, capacity)
        self.airfield_stoppage_dual = [0] * len(airport_parking_constraint_list)

    def pre_traversal(self, aircraft_num: int) -> dict:
        """
        将飞机id为aircraft_num的飞机能执行的航班，遍历并标记一遍
        # 若一个航班可执行，则该航班的所有后继航班都可执行
        :param aircraft_num:
        :return: 返回一个飞机的可执行航班的复制表
        """
        airline_forbid: set = self.flight_data.airline_aircraft_forbid[aircraft_num]
        graph_node_list_cp = dict()
        zero_time = timedelta(minutes=0)
        self.graph_node_list[-aircraft_num].adjust_list[zero_time].available.add(aircraft_num)
        graph_node_list_cp[-aircraft_num] = deep_copy(self.graph_node_list[-aircraft_num])  # 用到的时候才复制相关信息
        queue = [(-aircraft_num, zero_time)]
        while queue:
            current_mark = queue.pop(0)
            current_node_num, current_adjust_time = current_mark
            current_graph_node_cp: GraphNode = graph_node_list_cp[current_node_num]
            current_adjust_item_cp: AdjustItem = current_graph_node_cp.adjust_list[current_adjust_time]
            # 加入后继
            traversed_node_num = set()
            for suc_mark in current_adjust_item_cp.suc:
                suc_node_num, suc_adjust_time = suc_mark
                suc_node: GraphNode = self.graph_node_list[suc_node_num]
                suc_flight_info = suc_node.flight_info
                if (suc_flight_info['dp'], suc_flight_info['ap']) in airline_forbid:
                    continue
                suc_adjust_item: AdjustItem = suc_node.adjust_list[suc_adjust_time]
                suc_adjust_item.available.add(aircraft_num)
                traversed_node_num.add(suc_node_num)
                if suc_mark not in queue:
                    queue.append(suc_mark)
            # 深复制节点数据
            for tnn in traversed_node_num:
                if tnn not in graph_node_list_cp.keys():
                    graph_node_list_cp[tnn] = deep_copy(self.graph_node_list[tnn])
                else:
                    orig_graph_node = self.graph_node_list[tnn]
                    for at, ati in graph_node_list_cp[tnn].adjust_list.items():
                        ati: AdjustItem
                        ati.available = deep_copy(orig_graph_node.adjust_list[at].available)

        return graph_node_list_cp

    def topological_ordering(self, aircraft_num: int, graph_node_list_cp: dict):
        """
        对一架飞机的可执行航班进行拓扑排序
        若一个航班可执行，但并不是它的所有前驱航班都可执行。找到前驱中在可执行航班表中的航班，及其对应的边
        :param aircraft_num:
        :param graph_node_list_cp:
        :return:每个节点的邻接表
        """
        top_order_ls: list[tuple] = list()  # 记录该飞机所有可执行航班的拓扑排序
        adjacency_table: list[AdjTabItem] = list()
        node2num_map: dict[tuple[int, timedelta], int] = dict()
        node_cnt = 0
        edge_ls: list[tuple] = list()  # 记录该飞机可执行航班之间的连接
        edge_cost_ls = list()  # 记录该飞机可执行航班的执行成本，连接的成本为edge后继航班连接前驱航班的成本
        edge2num_map: dict[tuple[int, int], int] = dict()
        edge_cnt = 0

        graph_node_index: dict[int, list] = dict()

        init_mark = (-aircraft_num, timedelta(minutes=0))
        queue = [init_mark]
        node2num_map[init_mark] = node_cnt
        adjacency_table.append(AdjTabItem(num=node_cnt, info=init_mark))
        node_cnt += 1

        destination_airport = list()  # 存放终点机场信息
        while queue:
            current_node_num, current_adjust_time = None, None
            current_graph_node, current_adjust_item = None, None
            for mk in queue:
                node_num, adjust_time = mk
                graph_node: GraphNode = graph_node_list_cp[node_num]
                adjust_item: AdjustItem = graph_node.adjust_list[adjust_time]
                included = 0
                for pnl in adjust_item.pre:
                    pnn, pnat, c = pnl
                    pn: GraphNode = self.graph_node_list[pnn]
                    pnai: AdjustItem = pn.adjust_list[pnat]
                    if aircraft_num in pnai.available:
                        included = 1
                        break
                if not included:
                    current_node_num, current_adjust_time = node_num, adjust_time
                    current_graph_node, current_adjust_item = graph_node, adjust_item
                    break
            current_mark = (current_node_num, current_adjust_time)
            if current_node_num < 0:
                destination_airport.append(current_mark)
            top_order_ls.append(current_mark)
            queue.remove(current_mark)
            num = node2num_map[current_mark]
            adj_table_item = adjacency_table[num]

            # 加入后继
            for suc_mark in current_adjust_item.suc:
                suc_node_num, suc_adjust_time = suc_mark
                if suc_node_num not in graph_node_list_cp.keys():  # 不满足航线飞机约束
                    continue
                suc_node: GraphNode = self.graph_node_list[suc_node_num]
                suc_adjust_item: AdjustItem = suc_node.adjust_list[suc_adjust_time]
                if aircraft_num not in suc_adjust_item.available:
                    continue
                if suc_mark not in node2num_map.keys():
                    node2num_map[suc_mark] = node_cnt
                    suc_adj_table_item = AdjTabItem(num=node_cnt, info=suc_mark)
                    if suc_node_num not in graph_node_index.keys():
                        graph_node_index[suc_node_num] = [node_cnt]
                    else:
                        graph_node_index[suc_node_num].append(node_cnt)
                    adjacency_table.append(suc_adj_table_item)
                    node_cnt += 1
                suc_mark_num = node2num_map[suc_mark]
                suc_adj_table_item = adjacency_table[suc_mark_num]
                adj_table_item.suc.append(suc_mark_num)
                suc_adj_table_item.pre.append(num)

                if suc_mark not in queue:
                    queue.append(suc_mark)
                edge = (num, node2num_map[suc_mark])
                edge_ls.append(edge)
                edge2num_map[edge] = edge_cnt
                edge_cnt += 1
            # 删除当前复制节点的后继连接边与后继复制节点的前驱连接边
            while current_adjust_item.suc:
                suc_mark = current_adjust_item.suc.pop(0)
                suc_node_num, suc_adjust_time = suc_mark
                if suc_node_num not in graph_node_list_cp.keys():  # 不满足航线飞机约束
                    continue
                suc_node_cp: GraphNode = graph_node_list_cp[suc_node_num]
                suc_adjust_item_cp: AdjustItem = suc_node_cp.adjust_list[suc_adjust_time]
                if aircraft_num not in suc_adjust_item_cp.available:
                    continue
                cost = 0
                for pre_info in suc_adjust_item_cp.pre:
                    pre_info_node_num, pre_info_adjust_time, pre_info_cost = pre_info
                    if (pre_info_node_num, pre_info_adjust_time) == current_mark:
                        cost = pre_info_cost
                        break
                suc_adjust_item_cp.pre.remove((current_node_num, current_adjust_time, cost))
                edge_cost_ls.append(cost)
        # 为每一架飞机增加一个虚拟的沉落节点，保证一架飞机只有一个起点和一个终点
        sink_node = AdjTabItem(num=node_cnt, info=tuple())
        adjacency_table.append(sink_node)
        for da in destination_airport:
            da_num = node2num_map[da]
            da_adj_table_item = adjacency_table[da_num]
            da_adj_table_item.suc.append(node_cnt)
            sink_node.pre.append(da_num)
            virtual_edge = (da_num, node_cnt)
            edge_ls.append(virtual_edge)
            edge_cost_ls.append(0)
            edge2num_map[virtual_edge] = edge_cnt
            edge_cnt += 1

        self.aircraft_top_order[aircraft_num] = top_order_ls
        self.edge_cost_list[aircraft_num] = edge_cost_ls

        self.adjacency_table_list[aircraft_num] = adjacency_table
        self.node2num_map_list[aircraft_num] = node2num_map
        self.edge_ls_list[aircraft_num] = edge_ls
        self.edge2num_map_list[aircraft_num] = edge2num_map

        self.graph_node_index_list[aircraft_num] = graph_node_index

    def generate_association_matrix(self, aircraft_num: int):
        adjacency_table = self.adjacency_table_list[aircraft_num]
        edge2num_map = self.edge2num_map_list[aircraft_num]
        edge_len = len(edge2num_map)
        node_len = len(adjacency_table)
        node_arr = [0] * node_len
        node_arr[0] = 1
        node_arr[-1] = -1
        ass_matrix: list[list[int]] = list()
        for ati in adjacency_table:
            ati: AdjTabItem
            curr_num = ati.num
            row = [0] * edge_len
            for suc_num in ati.suc:
                edge = (curr_num, suc_num)
                edge_num = edge2num_map[edge]
                row[edge_num] = 1
            for pre_num in ati.pre:
                edge = (pre_num, curr_num)
                edge_num = edge2num_map[edge]
                row[edge_num] = -1
            ass_matrix.append(row)
        self.ass_matrix_list[aircraft_num] = ass_matrix
        self.node_attr_list[aircraft_num] = node_arr
        return ass_matrix

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
        self.slot_dual = [0] * len(self.exceeded_slots_capacity)

    def generate_terminal_airport_aircraft_type_matrix(self):
        airport_stop_tp = self.flight_data.airport_stop_tp
        aircraft_type_ls = self.flight_data.aircraft_type_ls
        terminal_num = 0
        for airport_num, type_info in airport_stop_tp.items():
            for ctp in aircraft_type_ls:
                needs = type_info[ctp]
                if needs > 0:
                    terminal_airport_mark = (airport_num, ctp)
                    self.terminal_airport_list.append(terminal_airport_mark)
                    self.terminal_airport_needs_list.append(needs)
                    self.terminal_airport_index_map[terminal_airport_mark] = terminal_num
                    terminal_num += 1
        self.terminal_airport_dual = [0] * len(self.terminal_airport_needs_list)

    def run(self):
        # 初始解
        self.generate_dep_arr_slot_matrix()
        self.generate_terminal_airport_aircraft_type_matrix()
        for aircraft_num in self.flight_data.aircraft_list.keys():
        # for aircraft_num in [3]:
            graph_node_list_cp = self.pre_traversal(aircraft_num)
            self.topological_ordering(aircraft_num, graph_node_list_cp)
            self.generate_association_matrix(aircraft_num)
            # 可并行
            edge_execution_cost = deep_copy(self.edge_cost_list[aircraft_num])
            edge2num_map = self.edge2num_map_list[aircraft_num]
            adjacency_table = self.adjacency_table_list[aircraft_num]
            for edge, edge_index in edge2num_map.items():
                from_node_num, airm_node_num = edge
                airm_adj_tab_item: AdjTabItem = adjacency_table[airm_node_num]
                airm_node_info = airm_adj_tab_item.info
                if not airm_node_info:
                    continue
                airm_graph_node_num = airm_node_info[0]
                graph_node_dual = self.flight_dual[airm_graph_node_num]
                edge_execution_cost[edge_index] += graph_node_dual

            sp_solver = ShortestPath(self.ass_matrix_list[aircraft_num], self.node_attr_list[aircraft_num],
                                     edge_execution_cost)
            sp_solver.add_mutex_constraint(self.flight_data.advance_flight_node_nums,
                                           self.graph_node_index_list[aircraft_num])
            sp_solver.solve()
            print('正在为飞机ID', aircraft_num, '初始化路径...')
            if sp_solver.is_int():
                print('最优解', sp_solver.optimal)
                print('包含航班个数', sum(sp_solver.solution))
            else:
                print('注意，非整数解')
