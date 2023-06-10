import pandas as pd
from datetime import datetime, timedelta
from dateutil.parser import parse as datetime_parse
from models.utils import Typhoon, TyphoonScene, SlotScene, MidstAirport
from models.utils import Airport, AirportTimeItem, GraphNode, AdjustItem


class FlightData(object):
    def __init__(self, min_turn_time: timedelta, duration_start: datetime, duration_end: datetime,
                 max_lead_time: timedelta, max_domestic_delay: timedelta, max_foreign_delay: timedelta):
        self.min_turn_time = min_turn_time
        self.duration_start = duration_start
        self.duration_end = duration_end

        self.max_lead_time = max_lead_time
        self.max_domestic_delay = max_domestic_delay
        self.max_foreign_delay = max_foreign_delay

        # read data
        data_path = r'D:\workspace\TianChiSeason2\data'
        self._flight_schedule = pd.read_csv(data_path + r'\flights_data.csv')
        self._airline_aircraft_ct = pd.read_csv(data_path + r'\airline_aircraft_ct.csv')
        self._flying_time_data = pd.read_csv(data_path + r'\flying_time_data.csv')
        self._turn_time_ct = pd.read_csv(data_path + r'\turn_time_ct.csv')

        self.schedule = None
        self.aircraft_id_list = None
        self._airport_ls = None
        self._airport_type_ls = None
        self._departure_airport_ls = None
        self._arrival_airport_ls = None
        self.node_cnt = 0
        self.airport_list = dict()
        self.typhoon_scene = TyphoonScene()
        self.slot_scene = SlotScene()
        self.schedule_groupby_departure = dict()
        self.graph_node_list = dict()
        self.origin_airport_list = dict()
        self.destination_airport_list = dict()

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

    def add_typhoon(self, typhoon_list: list):
        for typhoon in typhoon_list:
            airport_num, start_time, end_time = typhoon
            a_typhoon = Typhoon(airport_num, start_time, end_time)
            self.typhoon_scene[airport_num] = a_typhoon
            self.slot_scene.add_scene(airport_num, a_typhoon)

    @staticmethod
    def adjust_through_flight(graph_node: GraphNode, slots: list, dataframe: pd.DataFrame, mark='takeoff'):
        flight_info = graph_node.flight_info
        for si in slots:
            if mark == 'landing':
                adjust_time = si.start_time - dataframe['降落时间'].iloc[0]
            else:
                adjust_time = si.start_time - dataframe['起飞时间'].iloc[-1]
            adjust_info = AdjustItem(departure_time=flight_info['dpt'] + adjust_time,
                                     arrival_time=flight_info['avt'] + adjust_time,
                                     adjust_time=adjust_time)
            adjust_info.midst_airport = dataframe['降落机场'].iloc[0]
            adjust_info.midst_arrival_time = dataframe['降落时间'].iloc[0] + adjust_time
            adjust_info.midst_departure_time = dataframe['起飞时间'].iloc[-1] + adjust_time
            si.fall_in.append((graph_node.key, adjust_time))
            graph_node.adjust_list[adjust_info.adjust_time] = adjust_info
        return graph_node

    def selection_data(self, aircraft_id: int):
        self.schedule = self._flight_schedule[self._flight_schedule['飞机ID'] <= aircraft_id]
        self.schedule.loc[:, ['起飞时间']] = self.schedule['起飞时间'].apply(datetime_parse)
        self.schedule.loc[:, ['降落时间']] = self.schedule['降落时间'].apply(datetime_parse)
        self.schedule = self.schedule[self.schedule['起飞时间'] >= self.duration_start - timedelta(hours=6)]
        self.aircraft_id_list = set(list(self.schedule['飞机ID']))
        self._airport_type_ls = set(list(self.schedule['机型']))
        self._departure_airport_ls = set(list(self.schedule['起飞机场']))
        self._arrival_airport_ls = set(list(self.schedule['降落机场']))
        self._airport_ls = self._departure_airport_ls | self._arrival_airport_ls

        for ap in self._airport_ls:
            self.airport_list[ap] = Airport(ap)

        normal_flight = []
        through_flight = []
        strengthen_flight = []
        schedule_groupby_cid = self.schedule.groupby(by='飞机ID')
        for cid, groupby_cid in schedule_groupby_cid:
            groupby_cid = groupby_cid.sort_values(by='起飞时间')

            for i in range(len(groupby_cid)):
                frame = groupby_cid.iloc[i]
                if frame['起飞时间'] >= self.duration_start:
                    origin_time = frame['起飞时间']
                    origin_airport = frame['起飞机场']
                    if origin_airport not in self.origin_airport_list.keys():
                        self.origin_airport_list[origin_airport] = AirportTimeItem(origin_airport, origin_time)
                    elif self.origin_airport_list[origin_airport].time > origin_time:
                        self.origin_airport_list[origin_airport] = AirportTimeItem(origin_airport, origin_time)
                    break
            destination_airport = groupby_cid['降落机场'].iloc[-1]
            destination_time = groupby_cid['降落时间'].iloc[-1]
            if destination_airport not in self.destination_airport_list.keys():
                self.destination_airport_list[destination_airport] = AirportTimeItem(destination_airport,
                                                                                     destination_time)
            elif self.destination_airport_list[destination_airport].time < destination_time:
                self.destination_airport_list[destination_airport] = AirportTimeItem(destination_airport,
                                                                                     destination_time)

            schedule_groupby_date = groupby_cid.groupby(by='日期')
            for date, groupby_date in schedule_groupby_date:
                schedule_groupby_fno = groupby_date.groupby(by='航班号')
                for fno, dataframe in schedule_groupby_fno:
                    # dataframe = dataframe.sort_values(by='起飞时间')
                    if dataframe['起飞时间'].iloc[0] < self.duration_start:
                        if len(dataframe) > 1 and dataframe['起飞时间'].iloc[1] > self.duration_start:
                            dataframe = dataframe[dataframe['起飞时间'] > self.duration_start]
                            print("特殊航班，作为正好位于恢复期的联程后续航班，不可取消，只能调整")
                            print(dataframe)
                        else:
                            continue

                    flight_info = dict()
                    flight_info['attr'] = 'flight'
                    flight_info['cid'], flight_info['date'], flight_info['fno'] = cid, date, fno
                    flight_info['fids'] = dataframe['航班ID'].tolist()
                    flight_info['dp'], flight_info['ap'] = dataframe['起飞机场'].iloc[0], dataframe['降落机场'].iloc[-1]
                    flight_info['dpt'], flight_info['avt'] = dataframe['起飞时间'].iloc[0], dataframe['降落时间'].iloc[-1]
                    flight_info['tp'], flight_info['dom'] = dataframe['机型'].iloc[0], dataframe['国际/国内'].iloc[0]
                    flight_info['pn'], flight_info['tpn'] = dataframe['旅客数'].sum(), dataframe['联程旅客数'].iloc[0]
                    flight_info['sn'], flight_info['para'] = dataframe['座位数'].sum(), dataframe['重要系数'].sum()
                    flight_info['ma'] = None

                    graph_node = GraphNode(self.node_cnt, flight_info)
                    if len(dataframe) > 1:
                        flight_info['attr'] = 'through'
                        landing_airport = dataframe['降落机场'].iloc[0]
                        landing_time = dataframe['降落时间'].iloc[0]
                        takeoff_airport = dataframe['起飞机场'].iloc[-1]
                        takeoff_time = dataframe['起飞时间'].iloc[-1]
                        turn_time = takeoff_time - landing_time
                        flight_info['ma'] = MidstAirport(landing_airport, landing_time, takeoff_time)
                        if landing_airport in self.typhoon_scene.keys():
                            is_landing_forbid = self.typhoon_scene[landing_airport].landing_forbid(landing_time)
                            is_takeoff_forbid = self.typhoon_scene[takeoff_airport].takeoff_forbid(takeoff_time)
                        else:
                            is_landing_forbid, is_takeoff_forbid = False, False
                        if is_landing_forbid or is_takeoff_forbid:
                            slots = self.slot_scene[landing_airport][0]
                            if flight_info['dom'] == '国内':
                                # 尝试拉直
                                flight_info['attr'] = 'straighten'
                                straighten_flight_key = str(flight_info['dp']) + '-' + str(flight_info['ap']) + '-' + \
                                                        str(flight_info['tp'])
                                if straighten_flight_key in self.flying_time.keys():
                                    straighten_flying_time = timedelta(
                                        minutes=int(self.flying_time[straighten_flight_key]))
                                else:
                                    straighten_flying_time = flight_info['avt'] - flight_info['dpt'] - turn_time
                                straighten = AdjustItem(flight_info['dpt'], flight_info['dpt'] + straighten_flying_time)
                                straighten.cancelled_passenger_num = dataframe['联程旅客数'].iloc[0]
                                straighten.cost += 750 * flight_info['para']
                                graph_node.adjust_list[timedelta(minutes=0)] = straighten
                                strengthen_flight.append(graph_node.key)

                            # if is_landing_forbid:
                            # 尝试降落延误
                            if flight_info['dom'] == '国内':
                                latest_delayed_landing_time = dataframe['降落时间'].iloc[0] + self.max_domestic_delay
                            else:
                                latest_delayed_landing_time = dataframe['降落时间'].iloc[0] + self.max_foreign_delay

                            slot_start_time = self.typhoon_scene[landing_airport].end_time
                            landing_fallin_slot = slots.landing_slot.midst_eq(slot_start_time,
                                                                              latest_delayed_landing_time)
                            graph_node = self.adjust_through_flight(graph_node, landing_fallin_slot, dataframe,
                                                                    'landing')
                            takeoff_fallin_slot = slots.takeoff_slot.midst_eq(slot_start_time+turn_time,
                                                                              latest_delayed_landing_time+turn_time)
                            while takeoff_fallin_slot:
                                si = takeoff_fallin_slot.pop(0)
                                si.fall_in.append((graph_node.key, si.start_time-turn_time))

                            if is_takeoff_forbid:
                                # 尝试起飞提前
                                earliest_advance_time = dataframe['起飞时间'].iloc[-1] - self.max_lead_time
                                earliest_landing_time = earliest_advance_time - turn_time
                                gap = self.typhoon_scene[landing_airport].landing_forbid_start() - earliest_landing_time
                                if gap > timedelta(minutes=0):
                                    slot_end_time = min(earliest_advance_time + gap,
                                                        self.typhoon_scene[landing_airport].start_time)
                                    takeoff_fallin_slot = slots.takeoff_slot.midst_eq(earliest_advance_time,
                                                                                      slot_end_time)
                                    graph_node = self.adjust_through_flight(graph_node, takeoff_fallin_slot, dataframe)

                        through_flight.append(graph_node.key)
                    else:
                        normal_flight.append(graph_node.key)
                    self.graph_node_list[graph_node.key] = graph_node
                    self.airport_list[flight_info['dp']].flight_list.append(self.node_cnt)
                    self.node_cnt += 1
        print('拉直航班个数', len(strengthen_flight))
        print(strengthen_flight)
        print('联程航班个数', len(through_flight))
        print('单程航班个数', len(normal_flight))


if __name__ == '__main__':
    pass
