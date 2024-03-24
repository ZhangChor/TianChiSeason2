from datetime import datetime, timedelta

import pandas as pd
from dateutil.parser import parse as datetime_parse

from models.utils import Airport, GraphNode, AdjustItem
from models.utils import Typhoon, TyphoonScene, SlotScene, MidstAirport


class FlightData(object):
    def __init__(self, min_turn_time: timedelta, duration_start: datetime, duration_end: datetime,
                 max_domestic_delay: timedelta, max_foreign_delay: timedelta,
                 split_time: timedelta, slot_capacity: int, workspace:str):
        self.min_turn_time = min_turn_time
        self.duration_start = duration_start
        self.duration_end = duration_end

        # self.max_lead_time = max_lead_time
        self.max_domestic_delay = max_domestic_delay
        self.max_foreign_delay = max_foreign_delay

        self.split_time = split_time
        self.slot_capacity = slot_capacity

        # 模式改变
        self.compare = True

        # read data
        self.workspace_path = workspace
        data_path = self.workspace_path + r"/data"
        self._flight_schedule = pd.read_csv(data_path + r'/flights_data.csv')
        self._airline_aircraft_ct = pd.read_csv(data_path + r'/airline_aircraft_ct.csv')
        self._flying_time_data = pd.read_csv(data_path + r'/flying_time_data.csv')
        self._turn_time_ct = pd.read_csv(data_path + r'/turn_time_ct.csv')

        self.aircraft_volume = 0
        self.schedule = None
        self.airport_ls = None
        self.aircraft_type_ls = None
        self.departure_airport_ls = None
        self.arrival_airport_ls = None
        self.graph_node_cnt = 0
        self.adjust_item_cnt = 0
        self.tip_node_cnt = -1
        self._aircraft_num = 0
        self.airport_list = dict()
        self.aircraft_list = dict()
        self.typhoon_scene = TyphoonScene()
        self.slot_scene = SlotScene(split_time, slot_capacity)
        self.schedule_groupby_departure = dict()
        self.graph_node_list = dict()
        self.airport_stop_tp = dict()  # 机场停机类型数
        self.destination_airport = dict()  # 记录每架飞机的目的机场
        self._airport_num_to_graph_num_map = dict()
        self.mutex_flight_node_nums = set()  # 统计可能产生节点互斥的航班的node num

        self.flying_time = dict()
        for i in range(len(self._flying_time_data)):
            item = self._flying_time_data.iloc[i]
            key = str(item['起飞机场']) + '-' + str(item['降落机场']) + '-' + str(item['飞机机型'])
            self.flying_time[key] = item['飞行时间（分钟）']
        self.turn_time = dict()
        for i in range(len(self._turn_time_ct)):
            item = self._turn_time_ct.iloc[i]
            key = str(item['进港航班ID']) + '-' + str(item['出港航班ID'])
            self.turn_time[key] = (item['最短转机时限（分钟）'], item['中转旅客人数'])
        self.airline_aircraft_forbid = dict()
        for i in range(len(self._airline_aircraft_ct)):
            item = self._airline_aircraft_ct.iloc[i]
            key = item['飞机ID']
            # daf = str(item['起飞机场']) + '-' + str(item['降落机场'])
            daf = (item['起飞机场'], item['降落机场'])
            if key not in self.airline_aircraft_forbid.keys():
                self.airline_aircraft_forbid[key] = set()
            forbid_set = self.airline_aircraft_forbid[key]
            forbid_set.add(daf)

    def add_typhoon(self, typhoon_list: list):
        for typhoon in typhoon_list:
            airport_num, start_time, end_time = typhoon
            a_typhoon = Typhoon(airport_num, start_time, end_time)
            self.typhoon_scene[airport_num] = a_typhoon
            self.slot_scene.add_scene(airport_num, a_typhoon)

    def adjust_through_flight(self, graph_node: GraphNode, slots: list, dataframe: pd.DataFrame, mark='takeoff'):
        if not slots:
            return graph_node
        flight_info = graph_node.flight_info
        for si in slots:
            if mark == 'landing':
                adjust_time = si.start_time - dataframe['降落时间'].iloc[0]
            else:
                adjust_time = si.start_time - dataframe['起飞时间'].iloc[-1]
            adjust_info = AdjustItem(departure_time=flight_info['dpt'] + adjust_time,
                                     arrival_time=flight_info['avt'] + adjust_time,
                                     adjust_time=adjust_time, node_num=graph_node.key)
            self.adjust_item_cnt += 1
            adjust_info.midst_airport = dataframe['降落机场'].iloc[0]
            adjust_info.midst_arrival_time = dataframe['降落时间'].iloc[0] + adjust_time
            adjust_info.midst_departure_time = dataframe['起飞时间'].iloc[-1] + adjust_time
            si.fall_in.append((graph_node.key, adjust_time))
            graph_node.adjust_list[adjust_info.adjust_time] = adjust_info
        return graph_node

    def selection_data(self, aircraft_id: int, start_time=None, end_time=None):
        self.aircraft_volume = aircraft_id
        # self.schedule = self._flight_schedule[self._flight_schedule['飞机ID'].isin(aircraft_id)]
        self.schedule: pd.DataFrame = self._flight_schedule[self._flight_schedule['飞机ID'] <= aircraft_id]
        self.schedule.loc[:, ['起飞时间']] = self.schedule['起飞时间'].apply(datetime_parse)
        self.schedule.loc[:, ['降落时间']] = self.schedule['降落时间'].apply(datetime_parse)
        if start_time is not None:
            self.schedule = self.schedule[start_time <= self.schedule['起飞时间']]
        if end_time is not None:
            self.schedule = self.schedule[self.schedule['降落时间'] <= end_time]
        self.aircraft_type_ls = set(list(self.schedule['机型']))
        self.departure_airport_ls = set(list(self.schedule['起飞机场']))
        self.arrival_airport_ls = set(list(self.schedule['降落机场']))
        self._aircraft_num = len(set(list(self.schedule['飞机ID'])))
        aircraft_num = -self._aircraft_num - 1
        self.airport_ls = self.departure_airport_ls | self.arrival_airport_ls
        zero_time = timedelta(minutes=0)

        for ap in self.airport_ls:
            self.airport_list[ap] = Airport(ap, self.aircraft_type_ls)

        normal_flight = []
        cn2en = {
            '航班ID': 'fids',
            '日期': 'date',
            '国际/国内': 'dom',
            '航班号': 'fno',
            '起飞机场': 'dp',
            '降落机场': 'ap',
            '起飞时间': 'dpt',
            '降落时间': 'avt',
            '飞机ID': 'cid',
            '机型': 'tp',
            '旅客数': 'pn',
            '联程旅客数': 'tpn',
            '座位数': 'sn',
            '重要系数': 'para'
        }
        schedule_groupby_cid = self.schedule.groupby(by='飞机ID')
        for cid, groupby_cid in schedule_groupby_cid:
            groupby_cid = groupby_cid.sort_values(by='起飞时间')
            # 统计出发与到达机场
            for i in range(len(groupby_cid)):
                start_frame = groupby_cid.iloc[i + 1]
                if start_frame['起飞时间'] >= self.duration_start:
                    end_frame = groupby_cid.iloc[i]
                    origin_flight = dict()
                    origin_flight['attr'] = "departure"
                    origin_flight['cid'], origin_flight['fno'] = end_frame['飞机ID'], end_frame['航班号']
                    origin_flight['tp'], origin_flight['pn'] = end_frame['机型'], end_frame['旅客数']
                    origin_flight['tpn'], origin_flight['sn'] = end_frame['联程旅客数'], end_frame['座位数']
                    origin_flight['fids'] = end_frame['航班ID']
                    origin_flight['cost'] = 0
                    origin_flight['tmk'] = False
                    if end_frame['起飞时间'] >= self.duration_start:  # 恢复期开始前没有航班
                        origin_flight['ap'] = end_frame['起飞机场']
                        origin_flight['avt'] = end_frame['起飞时间'] - self.min_turn_time
                        origin_flight['pn'], origin_flight['tpn'] = 0, 0
                    else:  # 恢复期开始前有航班
                        origin_flight['ap'], origin_flight['avt'] = end_frame['降落机场'], end_frame['降落时间']
                    departure_node = GraphNode(self.tip_node_cnt, origin_flight)
                    origin_adjust = AdjustItem(self.tip_node_cnt, self.duration_start, origin_flight['avt'], zero_time)
                    self.adjust_item_cnt += 1
                    departure_node.adjust_list[zero_time] = origin_adjust
                    self.graph_node_list[self.tip_node_cnt] = departure_node
                    self.tip_node_cnt -= 1
                    self.aircraft_list[cid] = departure_node
                    break
            # 统计每个机场最终停的飞机类型的数量
            final_flight = groupby_cid.iloc[-1]
            tp = final_flight['机型']
            self.airport_list[final_flight['降落机场']].terminal_ctp[tp] += 1
            self.destination_airport[cid] = final_flight['降落机场']

            schedule_groupby_date = groupby_cid.groupby(by='日期')
            for date, groupby_date in schedule_groupby_date:
                schedule_groupby_fno = groupby_date.groupby(by='航班号')
                for fno, dataframe in schedule_groupby_fno:
                    if dataframe['起飞时间'].iloc[0] < self.duration_start:
                        if len(dataframe) > 1 and dataframe['起飞时间'].iloc[1] > self.duration_start:
                            dataframe = dataframe[dataframe['起飞时间'] > self.duration_start]
                            print("特殊航班，作为正好位于恢复期的联程后续航班，不可取消，只能调整", self.graph_node_cnt)
                            print(dataframe)
                        else:
                            continue
                    dataframe: pd.DataFrame
                    for _, row in dataframe.iterrows():
                        flight_info = dict()
                        info_dict = row.to_dict()
                        for k, v in info_dict.items():
                            flight_info[cn2en[k]] = v

                        flight_info['attr'] = 'flight'
                        flight_info['cost'] = 0
                        flight_info['tmk'] = False  # 台风标记，False表示不受台风影响，True表示受台风影响
                        flight_info['cmk'] = False  # 机场关闭标记

                        graph_node = GraphNode(self.graph_node_cnt, flight_info)
                        normal_flight.append(graph_node.key)
                        self.graph_node_list[graph_node.key] = graph_node
                        self.airport_list[flight_info['dp']].departure_flight_list.append(self.graph_node_cnt)
                        self.airport_list[flight_info['ap']].arrival_flight_list.append(self.graph_node_cnt)
                        self.graph_node_cnt += 1

        print("包含机场个数", len(self.airport_ls))
        # print('拉直航班个数', len(strengthen_flight))
        # print(strengthen_flight)
        # print('联程航班个数', len(through_flight))
        # print(through_flight)
        print('单程航班个数', len(normal_flight))
        for v in self.airport_list.values():
            v: Airport
            ctp = v.terminal_ctp
            if sum(ctp == 0) < len(self.aircraft_type_ls):
                self.airport_stop_tp[v.airport_num] = ctp
        for p, ctp in self.airport_stop_tp.items():
            flight_info = dict()
            flight_info['dp'], flight_info['ap'] = p, p
            flight_info['dpt'] = self.duration_end
            flight_info['ma'] = None
            flight_info['cost'] = 0
            graph_node = GraphNode(aircraft_num, flight_info)
            graph_node.adjust_list[zero_time] = AdjustItem(aircraft_num, flight_info['dpt'] + self.min_turn_time,
                                                           flight_info['dpt'] + self.min_turn_time, zero_time)
            self.adjust_item_cnt += 1
            self.graph_node_list[aircraft_num] = graph_node
            self._airport_num_to_graph_num_map[p] = aircraft_num
            aircraft_num -= 1

    def get_adjust_item(self, adjust_key: tuple):
        node_num, adjust_minute = adjust_key
        if node_num in self.graph_node_list.keys():
            node: GraphNode = self.graph_node_list[node_num]
            adjust_time = timedelta(minutes=adjust_minute)
            if adjust_time in node.adjust_list.keys():
                return node.adjust_list[adjust_time]
        return None

    def get_arrival_airport_graph_node(self, arrival_airport_num: int) -> GraphNode:
        if arrival_airport_num in self._airport_num_to_graph_num_map.keys():
            graph_node_num = self._airport_num_to_graph_num_map[arrival_airport_num]
            return self.graph_node_list[graph_node_num]

