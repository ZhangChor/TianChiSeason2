import pandas as pd
from datetime import datetime, timedelta
from dateutil.parser import parse as datetime_parse
from models.utils import dataframe_item
from models.utils import TyphoonScene


class FlightData(object):
    def __init__(self):
        self.min_turn_time = timedelta(minutes=50)
        self.duration_start = datetime(year=2017, month=5, day=6, hour=6)
        self.duration_end = datetime(year=2017, month=5, day=9, hour=0)

        # read data
        data_path = r'D:\workspace\TianChiSeason2\data'
        self._flight_schedule = pd.read_csv(data_path + r'\flights_data.csv')
        self._airline_aircraft_ct = pd.read_csv(data_path + r'\airline_aircraft_ct.csv')
        self._flying_time_data = pd.read_csv(data_path + r'\flying_time_data.csv')
        self._turn_time_ct = pd.read_csv(data_path + r'\turn_time_ct.csv')

        self.schedule = None
        self.aircraft_id_list = None
        self.typhoon_scene = TyphoonScene()
        self.selection_schedule = dataframe_item(drop=True)

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
            self.typhoon_scene.add_typhoon(airport_num=airport_num, start_time=start_time, end_time=end_time)

    def selection_data(self, aircraft_id: int):
        self.schedule = self._flight_schedule[self._flight_schedule['飞机ID'] < aircraft_id]
        self.schedule.loc[:, ['起飞时间']] = self.schedule['起飞时间'].apply(datetime_parse)
        self.schedule.loc[:, ['降落时间']] = self.schedule['降落时间'].apply(datetime_parse)
        self.aircraft_id_list = set(list(self.schedule['飞机ID']))

        schedule_groupby = self.schedule.groupby(by=['飞机ID', '日期', '航班号'])

        for keys, dataframe in schedule_groupby:
            dataframe = dataframe.sort_values(by='起飞时间')
            temp = dataframe_item()
            temp.cid, temp.date, temp.fno = keys
            temp.at[0, 'fids'] = dataframe['航班ID'].tolist()
            temp.dp = dataframe['起飞机场'].iloc[0]
            temp.ap = dataframe['降落机场'].iloc[-1]
            temp.dpt = dataframe['起飞时间'].iloc[0]
            temp.avt = dataframe['降落时间'].iloc[-1]
            temp.type = dataframe['机型'].iloc[0]
            temp.tpn = dataframe['联程旅客数'].iloc[0]
            temp.dom = dataframe['国际/国内'].iloc[0] == '国内'
            temp.para = dataframe['重要系数'].sum()
            temp.pn = dataframe['旅客数'].sum()
            temp.sn = dataframe['座位数'].sum()
            if len(dataframe) < 2:
                temp.attr = 'flight'
            else:
                temp.attr = 'through'
                if dataframe['降落机场'].iloc[0] in self.typhoon_scene.airport_list and (
                        self.typhoon_scene[dataframe['降落机场'].iloc[0]].landing_forbid(dataframe['降落时间'].iloc[0]) or
                        self.typhoon_scene[dataframe['降落机场'].iloc[0]].takeoff_forbid(dataframe['起飞时间'].iloc[-1])
                ) and temp.dom.iloc[0]:
                    temp.attr = 'straighten'
                    straighten_flight_key = str(temp.dp) + '-' + str(temp.ap) + '-' + str(temp.type)
                    if straighten_flight_key in self.flying_time.keys():
                        straighten_flying_time = timedelta(minutes=self.flying_time[straighten_flight_key])
                    else:
                        straighten_flying_time = dataframe['降落时间'].iloc[-1] - dataframe['起飞时间'].iloc[0]
                    temp.avt = temp.dpt + straighten_flying_time
            self.selection_schedule = pd.concat([self.selection_schedule, temp], ignore_index=True)
        # self.selection_schedule = self.selection_schedule.sort_values(by='dpt')
        print(f'flight num = {len(self.selection_schedule[self.selection_schedule["attr"] == "flight"])}')
        print(f'through num = {len(self.selection_schedule[self.selection_schedule["attr"]== "through"])}')
        print(f'straighten num = {len(self.selection_schedule[self.selection_schedule["attr"] == "straighten"])}')


if __name__ == '__main__':
    flight_data = FlightData()
    AIRCRAFT_NUM = 43
    typhoon_list = [(49, datetime(2017, 5, 6, 14), datetime(2017, 5, 7, 17)),
                    (50, datetime(2017, 5, 6, 14), datetime(2017, 5, 7, 17)),
                    (61, datetime(2017, 5, 6, 14), datetime(2017, 5, 7, 17))]
    flight_data.add_typhoon(typhoon_list)
    flight_data.selection_data(AIRCRAFT_NUM)


