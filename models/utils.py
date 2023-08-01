from pandas import Series
from datetime import timedelta, datetime


class SceneList(object):
    def __init__(self):
        self.scene_num = 0
        self.airport_list = list()
        self.scene_list = dict()

    def add_scene(self, airport: int, scene):
        if airport not in self.scene_list.keys():
            self.scene_list[airport] = [scene]
        else:
            self.scene_list[airport].append(scene)
        self.scene_num += 1
        self.airport_list.append(airport)

    def __getitem__(self, item) -> list or bool:
        if item in self.airport_list:
            return self.scene_list[item]
        else:
            return False


class Typhoon(object):
    def __init__(self, airport_num: int, start_time: datetime, end_time: datetime):
        self.airport_num = airport_num
        self.start_time = start_time
        self.end_time = end_time

    def landing_forbid(self, time: datetime):
        # 台风场景开始前2个小时就禁止降落
        return self.start_time - timedelta(hours=2) <= time <= self.end_time

    def takeoff_forbid(self, time: datetime):
        return self.start_time <= time <= self.end_time

    def landing_forbid_start(self):
        return self.start_time - timedelta(hours=2)


class TyphoonScene(dict):
    pass


class AirportClose(object):
    def __init__(self, airport_num: int, close_time: timedelta, open_time: timedelta,
                 effective_date: datetime, expiration_date: datetime):
        self.airport_num = airport_num
        self.close_time = close_time
        self.open_time = open_time
        self.effective_date = effective_date
        self.expiration_date = expiration_date

    def is_closed(self, time: datetime) -> bool:
        if self.effective_date <= time <= self.expiration_date + timedelta(days=1):
            current_time = timedelta(hours=time.hour, minutes=time.minute)
            if self.close_time <= current_time < self.open_time:
                return True
        return False

    def opening_time(self, time: datetime) -> datetime:
        return datetime(year=time.year, month=time.month, day=time.day) + self.open_time


class CloseScene(SceneList):
    pass


class SlotItem(object):
    def __init__(self, start_time: datetime, end_time: datetime, capacity: int):
        self.start_time = start_time
        self.end_time = end_time
        self.capacity = capacity

        self.fall_in = []

    def __lt__(self, other):
        return self.start_time < other.start_time

    def __eq__(self, other):
        return self.start_time == other.start_time

    def __repr__(self):
        return f'{self.start_time}-{self.end_time}:{self.capacity}'


class Slot(object):
    def __init__(self, split: timedelta):
        self.split = split
        self.slot_ls: list[SlotItem] = list()
        self.start_time = None
        self.end_time = None

    def add_slot(self, start_time: datetime, end_time: datetime, slot_capacity: int):
        self.start_time = start_time
        self.end_time = end_time
        point_start = start_time
        while point_start < end_time:
            point_end = point_start + self.split
            self.slot_ls.append(SlotItem(point_start, point_end, slot_capacity))
            point_start = point_end
        self.slot_ls = sorted(self.slot_ls)

    def midst_eq(self, start_time: datetime, end_time: datetime):
        ls = list()
        for si in self.slot_ls:
            if start_time <= si.start_time < end_time:
                ls.append(si)
        return ls

    def __getitem__(self, item: datetime) -> SlotItem:
        if self.start_time <= item <= self.end_time:
            for sl in self.slot_ls:
                if sl.start_time == item:
                    return sl
        raise IndexError("list index out of range")


class AirportSlot(object):
    def __init__(self, typhoon: Typhoon, before_time: timedelta, after_time: timedelta,
                 split_time: timedelta, split_capacity: int):
        self.airport = typhoon.airport_num
        self._max_capacity = 200
        self.takeoff_slot = Slot(split_time)
        self.takeoff_slot.add_slot(typhoon.start_time - before_time, typhoon.start_time, split_capacity)
        self.takeoff_slot.add_slot(typhoon.start_time - before_time - split_time, typhoon.start_time - before_time,
                                   slot_capacity=self._max_capacity)  # 额外的无限slot
        self.takeoff_slot.add_slot(typhoon.end_time, typhoon.end_time + after_time, split_capacity)
        self.takeoff_slot.add_slot(typhoon.end_time + after_time, typhoon.end_time + after_time + split_time,
                                   slot_capacity=self._max_capacity)  # 额外的无限slot

        self.landing_slot = Slot(split_time)
        self.landing_slot.add_slot(typhoon.start_time - timedelta(hours=2) - split_time,  # 额外的无限slot
                                   typhoon.start_time - timedelta(hours=2), slot_capacity=self._max_capacity)

        self.landing_slot.add_slot(typhoon.end_time, typhoon.end_time + after_time, split_capacity)
        self.landing_slot.add_slot(typhoon.end_time + after_time, typhoon.end_time + after_time + split_time,
                                   slot_capacity=self._max_capacity)  # 额外的无限slot


class SlotScene(SceneList):
    def __init__(self, split_time: timedelta, slot_capacity: int):
        super().__init__()
        self.before_time = timedelta(hours=1)
        self.after_time = timedelta(hours=2)
        self.split_time = split_time
        self.slot_capacity = slot_capacity

    def add_scene(self, airport: int, scene: Typhoon):
        airport_slot = AirportSlot(scene, self.before_time, self.after_time, self.split_time, self.slot_capacity)
        super().add_scene(airport, airport_slot)


class AirportStops(object):
    def __init__(self, start_time: datetime, end_time: datetime, airport_num: int, capacity: int):
        self.start_time = start_time
        self.end_time = end_time
        self.airport_num = airport_num
        self.capacity = capacity


class MidstAirport(object):
    def __init__(self, airport: int, arrival_time: datetime or None, departure_time: datetime or None):
        self.airport = airport
        self.arrival_time = arrival_time
        self.departure_time = departure_time


class AdjustItem(object):
    def __init__(self, node_num: int, departure_time: datetime, arrival_time: datetime,
                 adjust_time=timedelta(minutes=0)):
        self.node_num = node_num
        self.adjust_time = adjust_time
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.cancelled_passenger_num = 0
        self.delayed_passenger_num = 0
        self.cost = 0
        self.available = set()  # 记录哪些飞机可以执行该调整航班

        self.midst_airport = MidstAirport(-1, None, None)

        self.pre = []  # 存放前驱航班的node key, adjust time和connect cost
        self.suc = []  # 存放后继航班的node key与adjust time

    def __repr__(self):
        return f'{self.adjust_time} {self.midst_airport.arrival_time} {self.midst_airport.departure_time}'

    def mark(self):
        return self.node_num, timedelta_minutes(self.adjust_time)


class FlightInfo(dict):
    pass


class GraphNode(object):
    def __init__(self, key: int, flight_info: dict):
        self.key = key
        self.flight_info = flight_info
        self.adjust_list = dict()
        self.pres = set()  # 前驱航班

    # def __repr__(self):
    #     return f'{self.flight_info["fids"]}: {self.flight_info["dp"]}-{self.flight_info["ap"]}'


class NodeList(dict):
    pass


class Airport(object):
    def __init__(self, airport_num: int, ctp: set):
        self.airport_num = airport_num
        self.departure_flight_list = []
        self.arrival_flight_list = []
        self.terminal_ctp = Series(0, index=ctp)  # 每种类型的飞机的最终停在该机场的数量


class AirportList(dict):
    pass


class TipAirport(GraphNode):
    def __init__(self, key: int, flight_info: dict, ctp: set):
        super().__init__(key, flight_info)
        self.ctp = Series(0, index=ctp)


class CostInfo(object):
    def __init__(self, reduce_cost=0, exec_cost=0):
        self.reduce_cost: float = reduce_cost
        self.exec_cost: float = exec_cost
        self.best_pre: None or tuple = None
        self.route: list = list()  # route = [(node num, adjust minute)]
        self.pre_node: set = set()  # pre_node = {node num}

    def __repr__(self):
        return f'reduce cost: {self.reduce_cost}, best pre: {self.best_pre}'


def timedelta_minutes(time: timedelta) -> float:
    if time.days >= 0:
        return time.seconds / 60
    else:
        full_time = timedelta(days=-2 * time.days)
        positive_time = full_time - time
        return -positive_time.seconds / 60


class AdjTabItem(object):
    def __init__(self, num: int, info: tuple):
        self.num = num
        self.info = info
        self.pre = []
        self.suc = []

    def __repr__(self):
        return f'{self.num: {self.pre}-{self.suc}}'


if __name__ == '__main__':
    pass
