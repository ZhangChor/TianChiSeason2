from datetime import timedelta
from models.graph import Graph
from models.handing import FlightData
from models.utils import AirportParkingScene, AirfieldStoppages
from models.utils import GraphNode, AirportSlot, SlotItem, AdjTabItem, AdjustItem
from models.iterate import deep_copy


class MultiFlowProblem(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_list = self.flight_data.graph_node_list  # 可以用到的时候再复制
        self.airport_parking_scene = AirportParkingScene()
        self.airport_parking_map = dict()
        self.airport_parking_capacity = list()
        self.top_order = dict()  # 可执行航班的拓扑排序
        self.adjacency_table_list = dict()  # 储存邻接表
        self.node2num_map_list = dict()  # 储存可执行航班到在邻接矩阵中的行的指标
        self.edge_ls_list = dict()  # 储存可执行边
        self.edge2num_map_list = dict()  # 储存可执行边在邻接矩阵中的列的指标
        self.ass_matrix_list = dict()  # 储存邻接矩阵
        self.edge_cost_list = dict()  # 储存边的执行花费
        self.node_attr_list = dict()  # 存储node的出入度情况
        self.mutex_graph_node_edge_list = dict()
        self.exceeded_slots = list()  # 储存落入数量超过容量的slot信息
        self.exceeded_slots_capacity = list()  # 储存落入数量超过容量的slot的容量
        self.exceeded_slots_map = dict()  # 储存落入数据超过容量的slot的标号

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

    def generate_association_matrix(self):
        """
        遍历图中所有边，并生成相关矩阵
        :return:
        """
        top_order_ls: list[tuple] = list()  # 记录该飞机所有可执行航班的拓扑排序
        adjacency_table: list[AdjTabItem] = list()
        node2num_map: dict[tuple[int, timedelta], int] = dict()
        node_cnt = 0
        edge_ls: list[tuple] = list()  # 记录该飞机可执行航班之间的连接
        edge_cost_ls = list()  # 记录该飞机可执行航班的执行成本，连接的成本为edge后继航班连接前驱航班的成本
        edge2num_map: dict[tuple[int, int], int] = dict()
        edge_cnt = 0

        mutex_graph_node_edges = dict()  # 存放一个graph node的所有调整方案的所有后继边

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
            if current_node_num < -len(self.flight_data.aircraft_list):
                destination_airport.append(current_mark)
            top_order_ls.append(current_mark)
            queue.remove(current_mark)
            current_num = node2num_map[current_mark]
            adj_table_item = adjacency_table[current_num]

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
                    adjacency_table.append(suc_adj_table_item)
                    node_cnt += 1
                suc_mark_num = node2num_map[suc_mark]
                suc_adj_table_item = adjacency_table[suc_mark_num]
                adj_table_item.suc.append(suc_mark_num)
                suc_adj_table_item.pre.append(current_num)

                if suc_mark not in queue:
                    queue.append(suc_mark)
                edge = (current_num, node2num_map[suc_mark])
                edge_ls.append(edge)
                edge2num_map[edge] = edge_cnt
                if current_node_num in self.flight_data.mutex_flight_node_nums:
                    if current_node_num not in mutex_graph_node_edges.keys():
                        mutex_graph_node_edges[current_node_num] = [edge_cnt]
                    else:
                        mutex_graph_node_edges[current_node_num].append(edge_cnt)
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
                if suc_node_cp.key >= 0 and suc_node_cp.flight_info['cid'] != aircraft_num:  # 换机成本
                    cost += change_aircraft_para(suc_node_cp.flight_info['dpt'])
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

        self.top_order[aircraft_num] = top_order_ls
        self.edge_cost_list[aircraft_num] = edge_cost_ls

        self.adjacency_table_list[aircraft_num] = adjacency_table
        self.node2num_map_list[aircraft_num] = node2num_map
        self.edge_ls_list[aircraft_num] = edge_ls
        self.edge2num_map_list[aircraft_num] = edge2num_map

        self.mutex_graph_node_edge_list[aircraft_num] = mutex_graph_node_edges
