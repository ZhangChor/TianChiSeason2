from models.graph import Graph
from models.handing import FlightData
from models.utils import timedelta_minutes
from models.utils import GraphNode, AdjustItem, AdjTabItem
from pickle import dumps, loads
from datetime import timedelta
from sys import maxsize


def deep_copy(data):
    return loads(dumps(data))  # 代替copy.deepcopy


class ColumnGeneration(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_list = self.flight_data.graph_node_list  # 可以用到的时候再复制
        self.aircraft_top_order = dict()  # 每架飞机的可执行航班的拓扑排序都不一定一样

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
        edge_ls: list[tuple] = list()  # 记录该飞机可可执行航班之间的连接
        edge2num_map: dict[tuple[int, int], int] = dict()
        edge_cnt = 0

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
            edge2num_map[virtual_edge] = edge_cnt
            edge_cnt += 1

        self.aircraft_top_order[aircraft_num] = top_order_ls
        return adjacency_table, node2num_map, edge_ls, edge2num_map
    # todo 加入限制约束， 加入cost
    def generate_association_matrix(self, adjacency_table: list, node2num_map: dict,
                                    edge_ls: list, edge2num_map: dict):
        edge_len = len(edge_ls)
        ass_matrix: list[list[int]] = list()
        for ati in adjacency_table:
            ati: AdjTabItem
            curr_num = ati.num
            row = [0]*edge_len
            for suc_num in ati.suc:
                edge = (curr_num, suc_num)
                edge_num = edge2num_map[edge]
                row[edge_num] = 1
            for pre_num in ati.pre:
                edge = (pre_num, curr_num)
                edge_num = edge2num_map[edge]
                row[edge_num] = -1
            ass_matrix.append(row)
        return ass_matrix

    def find_shortest_path(self):
        pass
