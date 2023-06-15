from models.handing import FlightData
from models.utils import AdjustItem, GraphNode, Airport, AirportClose, CloseScene
from datetime import timedelta


class Graph(object):
    def __init__(self, flight_data: FlightData):
        self.flight_data = flight_data
        self.queue = []
        self.close_scene = CloseScene()
        self.typhoon_scene: dict = flight_data.typhoon_scene
        for tip_node in flight_data.aircraft_list.values():
            self.queue.append((tip_node.key, tip_node.adjust_list[timedelta(0)].adjust_time))

    def add_close(self, closed_list: list):
        for closed in closed_list:
            airport_num, close_time, open_time, effective_date, expiration_date = closed
            airport_closed = AirportClose(airport_num, close_time, open_time, effective_date, expiration_date)
            self.close_scene.add_scene(airport_num, airport_closed)

    def build_graph(self):
        node_list: dict = self.flight_data.graph_node_list
        airport_list: dict = self.flight_data.airport_list
        # dest_airport_list: dict = self.flight_data.dest_airport_list
        min_turn_time: timedelta = self.flight_data.min_turn_time
        max_domestic_delay: timedelta = self.flight_data.max_domestic_delay
        max_foreign_delay: timedelta = self.flight_data.max_foreign_delay
        zero_time = timedelta(minutes=0)
        max_adjust_item_num = timedelta(hours=2)/self.flight_data.split_time + 1
        while self.queue:
            print(len(self.queue), self.queue)
            current_node_num, adjust_time = self.queue.pop(0)
            current_node: GraphNode = node_list[current_node_num]
            current_flight_info: dict = current_node.flight_info
            current_adjust_info: AdjustItem = current_node.adjust_list[adjust_time]
            current_airport = current_flight_info['ap']
            current_time = current_adjust_info.arrival_time
            alter_flights: Airport = airport_list[current_airport]
            alter_flight_list = [201] if current_node_num == -24 else alter_flights.flight_list  # 特殊航班处理
            for nn in alter_flight_list:
                alter_flight_node: GraphNode = node_list[nn]
                alter_flight_info: dict = alter_flight_node.flight_info
                alter_flight_adjust: dict = alter_flight_node.adjust_list
                alter_flight_dp = alter_flight_info['dp']
                alter_flight_dpt = alter_flight_info['dpt']
                alter_flight_ap = alter_flight_info['ap']
                alter_flight_avt = alter_flight_info['avt']

                # 尝试在alter_flight_adjust中加入AdjustItem
                # if len(alter_flight_adjust) < max_adjust_item_num:
                if alter_flight_adjust:
                    max_delay_time = max_domestic_delay if alter_flight_info['dom'] == '国内' else max_foreign_delay

                    # 台风场景
                    if alter_flight_dp in self.typhoon_scene.keys():
                        is_takeoff_forbid_t = self.typhoon_scene[alter_flight_dp].landing_forbid(alter_flight_dpt)
                    else:
                        is_takeoff_forbid_t = False

                    if alter_flight_ap in self.typhoon_scene.keys():
                        is_landing_forbid_t = self.typhoon_scene[alter_flight_ap].landing_forbid(alter_flight_avt)
                    else:
                        is_landing_forbid_t = False

                    # 机场关闭场景
                    is_takeoff_forbid_c, is_landing_forbid_c = False, False
                    if alter_flight_dp in self.close_scene.airport_list:
                        for cd in self.close_scene[alter_flight_dp]:
                            cd: AirportClose
                            is_takeoff_forbid_c = cd.is_closed(alter_flight_dpt)
                            if is_takeoff_forbid_c:
                                if is_takeoff_forbid_t:
                                    is_takeoff_forbid_c = False
                                break
                    if alter_flight_ap in self.close_scene.airport_list:
                        for cd in self.close_scene[alter_flight_ap]:
                            cd: AirportClose
                            is_landing_forbid_c = cd.is_closed(alter_flight_avt)
                            if is_landing_forbid_c:
                                if is_landing_forbid_t:
                                    is_landing_forbid_c = False
                                break

                    # 正常连接
                    if min_turn_time <= alter_flight_dpt - current_time:  # 可以直接连接
                        delay_time = zero_time
                    elif min_turn_time <= alter_flight_dpt - current_time + max_delay_time:  # 可以通过延误连接
                        delay_time = current_time - alter_flight_dpt + min_turn_time
                    else:  # 无法连接
                        continue
                    adjust_info = AdjustItem(alter_flight_dpt + delay_time, alter_flight_info['avt'] + delay_time,
                                             delay_time)
                    if delay_time not in alter_flight_adjust.keys():
                        alter_flight_adjust[delay_time] = adjust_info

                # 尝试连接
                for afa in alter_flight_adjust.values():
                    afa: AdjustItem
                    if min_turn_time <= afa.departure_time - current_time:
                        if (current_node_num, adjust_time) not in afa.pre:
                            afa.pre.append((current_node_num, adjust_time))
                        if (nn, afa.adjust_time) not in current_adjust_info.suc:
                            current_adjust_info.suc.append((nn, afa.adjust_time))
                        if (nn, afa.adjust_time) not in self.queue:
                            self.queue.append((nn, afa.adjust_time))

