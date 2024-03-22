from datetime import timedelta

from models.handing import FlightData
from models.utils import GraphNode, AdjustItem, Airport


class ConnectNode(GraphNode):
    def __init__(self, key: int, flight_info: dict):
        super().__init__(key, flight_info)
        self.pre = list()
        self.suc = list()


class MultiLabel(object):
    """为所选航班数据，创建可行图，并调用多标签动态规划算法寻找最短路径

    - Step 1. 根据航班数据，为每个航班创建Node
    - Step 2. 根据Node的出发机场、到达机场、出发时间、到达时间和中转时间，构建可行图
    - Step 3. 对可行图使用多标签动态规划算法

    """

    def __init__(self, flight_data: FlightData):
        self.flight_data = flight_data
        # self.graph_node_list = flight_data.graph_node_list
        self.turn_time: dict = flight_data.turn_time
        self.queue = list()

        self.connect_graph_list = dict()
        for node_num, graph_node in flight_data.graph_node_list.items():
            graph_node: GraphNode
            self.connect_graph_list[node_num] = ConnectNode(node_num, graph_node.flight_info)

        zero_time = timedelta(seconds=0)
        for tip_node in flight_data.aircraft_list.values():
            self.queue.append((tip_node.adjust_list[zero_time].departure_time, tip_node.key))

    def built(self):
        """ 构建规则

        - Two nodes are directly connected if the airport where the first flight is completed is the same as the airport
        where the second flight begin.
        - Let the earlier departure flights point to later ones. The first flight's scheduled departure time must be
        earlier than the second flight's.

        :return:
        """
        # node_list: dict = self.flight_data.graph_node_list
        airport_list: dict = self.flight_data.airport_list
        # dest_airport_list: dict = self.flight_data.dest_airport_list
        min_turn_time: timedelta = self.flight_data.min_turn_time
        max_domestic_delay: timedelta = self.flight_data.max_domestic_delay
        max_foreign_delay: timedelta = self.flight_data.max_foreign_delay
        max_lead_time: timedelta = self.flight_data.max_lead_time

        zero_time = timedelta(minutes=0)
        while self.queue:
            self.queue.sort()
            current_mark = self.queue.pop(0)
            dpt, current_node_num = current_mark
            current_node: GraphNode = self.connect_graph_list[current_node_num]
            current_flight_info: dict = current_node.flight_info
            current_airport = current_flight_info['ap']
            current_time = current_flight_info['avt']
            alter_flights: Airport = airport_list[current_airport]
            landing_fid = current_flight_info['fids'][-1]
            # alter_flight_list = [201] if current_node_num == -24 else alter_flights.departure_flight_list  # 处理特殊航班
            alter_flight_list = alter_flights.departure_flight_list
            for alter_node_num in alter_flight_list:
                alter_flight_node: GraphNode = node_list[alter_node_num]
                alter_flight_info: dict = alter_flight_node.flight_info
                takeoff_fid = alter_flight_info['fids'][0]
                alter_flight_dp = alter_flight_info['dp']
                if alter_flight_dp != current_airport:  # 判断机场是否衔接
                    continue
                alter_flight_dpt = alter_flight_info['dpt']

                fids_key = str(landing_fid) + '-' + str(takeoff_fid)
                if fids_key in self.turn_time.keys():
                    turn_time_minute, endorsement_num = self.turn_time[fids_key]
                    turn_time = timedelta(minutes=int(turn_time_minute))
                else:
                    turn_time, endorsement_num = min_turn_time, 0
                # Trying connect
                if current_time + turn_time <= alter_flight_dpt:  # todo 增加相同fid的判别
                    current_adjust_item.suc.add(alter_flight_node.key)

                    pass
