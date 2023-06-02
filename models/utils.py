from pandas import DataFrame
from datetime import timedelta, datetime


def dataframe_item(drop=False) -> DataFrame:
    head = DataFrame(
        columns={'attr': '',  # Flight attributes
                 'fids': [],  # Flight ID
                 'fno': '',  # Flight No.
                 'cid': '',  # Aircraft ID
                 'dp': '',  # Departure airport
                 'ap': '',  # Arrival airport
                 'date': '',  # Date
                 'dpt': '',  # Departure time
                 'avt': '',  # Arrival time
                 'type': '',  # Aircraft type
                 'dom': '',  # Is Domestic
                 'para': 0,  # Flight importance parameter
                 'pn': 0,  # Passenger numbers
                 'tpn': 0,  # Through passenger numbers
                 'sn': 0,  # Seat numbers
                 'rsn': 0},  # Remain seat numbers
        index=[0]
    )
    if drop:
        return head.drop(index=0)
    return head


class Typhoon(object):
    def __init__(self, airport_num: int, start_time: datetime, end_time: datetime):
        self.airport_num = airport_num
        self.start_time = start_time
        self.end_time = end_time

    def landing_forbid(self, time: datetime):
        return self.start_time <= time <= self.end_time

    def takeoff_forbid(self, time: datetime):
        # 台风场景开始之后2小时之内，一般还允许飞机起飞
        return self.start_time + timedelta(hours=2) <= time <= self.end_time


class TyphoonScene(object):
    def __init__(self):
        self.scene_num = 0
        self.airport_list = []
        self.typhoon_list = []
        self._max_domestic_adv = timedelta(hours=6)
        self._max_domestic_delay = timedelta(hours=24)
        self._max_abroad_delay = timedelta(hours=36)

    def set_delay_n_adv(self, adv=6, delay=(24, 36)):
        self._max_domestic_adv = timedelta(hours=adv)
        dom, abr = delay
        self._max_domestic_delay = timedelta(hours=dom)
        self._max_abroad_delay = timedelta(hours=abr)

    def add_typhoon(self, airport_num: int, start_time: datetime, end_time: datetime):
        """
        添加一种台风场景
        :param airport_num: 机场编号
        :param start_time: 台风开始时间，以不允许飞机降落为准
        :param end_time: 台风结束时间
        :return:
        """
        if airport_num not in self.airport_list:
            self.airport_list.append(airport_num)
            self.typhoon_list.append(Typhoon(airport_num, start_time, end_time))
            self.scene_num += 1
        return self

    def __getitem__(self, airport_num: int) -> Typhoon or bool:
        """
        可以根据机场号获取相关机场台风场景信息
        :param airport_num: 机场编号
        :return: 若该机场没有台风场景，返回False，若有，返回该台风场景
        """
        if airport_num in self.airport_list:
            return self.typhoon_list[self.airport_list.index(airport_num)]
        else:
            return False

    def earliest_domestic_delays(self, airport_num: int) -> datetime:
        return self[airport_num].end_time - self._max_domestic_delay

    def earliest_abroad_delays(self, airport_num: int) -> datetime:
        return self[airport_num].start_time - self._max_abroad_delay

    def latest_domestic_advances(self, airport_num: int) -> datetime:
        return self[airport_num].start_time + self._max_domestic_adv
