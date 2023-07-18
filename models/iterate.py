from models.graph import Graph
from models.handing import FlightData
from models.utils import timedelta_minutes
from models.utils import CostInfo, GraphNode, AdjustItem
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

    def topological_ordering(self, aircraft_num: int):
        """"对一架飞机的可执行航班进行拓扑排序；对使用到的边和节点进行统计；
        判断图中是否出现了环，若出现了，记录下来，方便后续寻找最优路径"""

        airline_forbid: set = self.flight_data.airline_aircraft_forbid[aircraft_num]
        graph_node_list_cp = dict()
        dp_dist_list = dict()  # dp_dist_list = {(node_num: int, adjust_time: timedelta):CostInfo()}
        top_order = list()  # 记录该飞机所有可执行航班的拓扑排序
        delete_edge = list()  # 记录需要删除的边
        zero_time = timedelta(minutes=0)

        graph_node_list_cp[-aircraft_num] = deep_copy(self.graph_node_list[-aircraft_num])  # 用到的时候才复制相关信息

        dp_dist_list[(-aircraft_num, zero_time)] = CostInfo()
        queue = [(-aircraft_num, zero_time)]

        while queue:
            # 寻找入度为0的航班调整方案
            for adjust_info in queue:
                node_num, adjust_time = adjust_info
                node_num: int
                adjust_time: timedelta
                adjust_item_copy = graph_node_list_cp[node_num].adjust_list[adjust_time]
                if not adjust_item_copy.pre:
                    break
            current_mark = (node_num, adjust_time)
            queue.remove(current_mark)
            if (node_num, adjust_time) in top_order:
                pass
            top_order.append((node_num, adjust_time))
            current_node: GraphNode = self.graph_node_list[node_num]
            current_node_adjust_item: AdjustItem = current_node.adjust_list[adjust_time]
            dp_dist = dp_dist_list[(node_num, adjust_time)]
            # 加入后继
            for suc_info in current_node_adjust_item.suc:
                suc_node_num, suc_node_adjust_time = suc_info
                suc_node_num: int
                suc_node_adjust_time: timedelta
                suc_node: GraphNode = self.graph_node_list[suc_node_num]
                daf = (suc_node.flight_info['dp'], suc_node.flight_info['ap'])
                if daf in airline_forbid:
                    continue
                if suc_node_num not in graph_node_list_cp.keys():
                    graph_node_list_cp[suc_node_num] = deep_copy(self.graph_node_list[suc_node_num])
                suc_node_adjust_item = graph_node_list_cp[suc_node_num].adjust_list[suc_node_adjust_time]
                for pre_info in suc_node_adjust_item.pre:
                    pre_node_num, pre_adjust_time, pre_cost = pre_info
                    if (pre_node_num, pre_adjust_time) == current_mark:
                        suc_node_adjust_item.pre.remove(pre_info)
                        adjust_item_copy.suc.remove(suc_info)
                        break

                queue.append(suc_info)
                dp_dist_list[suc_info] = CostInfo()
            # 寻找最优前驱
            best_cost = maxsize
            best_pre_node_num, best_pre_adjust_time = None, None
            for pre_info in current_node_adjust_item.pre:
                pre_node_num, pre_adjust_time, cost = pre_info
                pre_node_num: int
                pre_adjust_time: timedelta
                cost: float
                pre_node_mark = (pre_node_num, pre_adjust_time)
                if pre_node_mark in dp_dist_list.keys() and cost < best_cost:
                    best_pre_node_num, best_pre_adjust_time = pre_node_num, pre_adjust_time
                    best_cost = cost
            # todo 判断当前节点是否已经出现在最优前驱的路径中
            best_pre_mark = (best_pre_node_num, best_pre_adjust_time)
            if not best_pre_node_num is None:
                dp_dist.best_pre, dp_dist.exec_cost = best_pre_mark, best_cost + dp_dist_list[best_pre_mark].exec_cost
                best_pre_dp_dist: CostInfo = dp_dist_list[best_pre_mark]
                if node_num in best_pre_dp_dist.pre_node:
                    """"把之前出现过的航班及其后续航班记录下来，作为删除边，后面处理；把当前这个连接处理为不可连接的边"""
                    pass

                else:
                    dp_dist.route = deep_copy(best_pre_dp_dist.route)
                    dp_dist.route.append(current_mark)
                    dp_dist.pre_node = deep_copy(best_pre_dp_dist.pre_node)
                    dp_dist.pre_node.add(node_num)
        self.aircraft_top_order[aircraft_num] = top_order
        return dp_dist_list

    def find_shortest_path(self):
        pass
