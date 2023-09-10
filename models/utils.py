from pandas import Series
from datetime import timedelta, datetime

import numpy as np
import csv


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
        return f'{self.start_time}~{self.end_time}:{self.capacity}'


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


class AirfieldStoppages(object):
    def __init__(self, airport_num: int, start_time: datetime, end_time: datetime, capacity: int):
        self.airport_num = airport_num
        self.start_time = start_time
        self.end_time = end_time
        self.capacity = capacity


class AirportParkingScene(dict):
    pass


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
        return f'{self.num}: {self.info}'


def dot_sum(ls: list, other: list):
    if len(ls) == len(other):
        return sum(np.array(ls) * np.array(other))
    else:
        raise 'LENGTH ERROR'


def change_aircraft_para(time: datetime):
    if time <= datetime(year=2017, month=5, day=6, hour=16):
        return 15
    else:
        return 5


class SolutionInfo(object):
    def __init__(self, graph_node_ls: dict, graph_node_strings: list, var_num_ls: list, cost: float,
                 iter_num: int, running_time: float):
        self.graph_node_ls = graph_node_ls
        self.graph_node_strings = graph_node_strings
        self.var_num_ls = var_num_ls
        self.aircraft_num = len(var_num_ls)
        self.scores = cost  # 得分（恢复成本）
        self.iter_num = iter_num
        self.running_time = timedelta(seconds=running_time)

        self.aircraft_type_conversion = 0  # 机型改变数量
        self.flight_cancellation = 0  # 取消航班数
        self.del_flights = 0  # 延误航班数量
        self.del_15m_flights = 0  # 延误15分钟以上航班数量
        self.del_30m_flights = 0  # 延误30分钟以上航班数量
        self.adv_flights = 0  # 提前航班数量
        self.adv_15m_flights = 0  # 提前15分钟以上航班数量
        self.adv_30m_flights = 0  # 提前30分钟以上航班数量
        self.straighten_flights = 0  # 拉直航班数量
        self.total_del_minutes = 0  # 总延误时间（分钟）
        self.total_adv_minutes = 0  # 总提前时间（分钟）
        self.swap_flights = 0  # 换机数量
        self.performed_flights = 0  # 计划执行航班数量
        self.make_up_flights = 0  # 补班数量

        self.avg_del_minutes = 0  # 平均延误时间
        self.avg_adv_minutes = 0  # 平均提前时间
        self.error_rate = 0  # 异常率（延误或提前大于15分钟航班/(总航班-取消航班数量）

        self.passenger_cancellation = 0  # 旅客取消人数
        self.passenger_delay_nums = 0  # 旅客延误人数
        self.passenger_delay_minutes = 0  # 旅客总延误时间
        self.seat_remains = 0  # 剩余座位数

    def time_str(self) -> str:
        times = self.running_time
        days = times.days
        hours, remainder = divmod(times.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        seconds_formatted = "{:.3f}".format(times.microseconds / 1000000)
        formatted_time = f"{days}_{hours}_{minutes}_{seconds}_{seconds_formatted}"
        return formatted_time

    def _get_cid(self, index: int) -> int:
        for cid in range(1, self.aircraft_num + 1):
            if index < sum(self.var_num_ls[:cid]):
                return cid

    def statistical_path_info(self, solution_x: list):
        graph_node_ls = self.graph_node_ls
        zero_time = timedelta(minutes=0)
        pas_15_time = timedelta(minutes=15)
        pas_30_time = timedelta(minutes=30)
        net_15_time = zero_time - pas_15_time
        net_30_time = zero_time - pas_30_time
        for i in range(len(solution_x)):
            if solution_x[i] == 1:
                cid = self._get_cid(i)
                tp = graph_node_ls[-cid].flight_info["tp"]
                route_strings = self.graph_node_strings[i]
                for graph_node_num, adjust_time in route_strings:
                    if graph_node_num < 0:
                        continue
                    graph_node: GraphNode = graph_node_ls[graph_node_num]
                    flight_info = graph_node.flight_info
                    adjust_item: AdjustItem = graph_node.adjust_list[adjust_time]
                    # begin statistical info
                    self.performed_flights += len(flight_info["fids"])
                    if adjust_time > zero_time:
                        self.del_flights += 1
                        delay_minutes = timedelta_minutes(adjust_time)
                        self.total_del_minutes += delay_minutes
                        self.passenger_delay_nums += flight_info["pn"]
                        self.passenger_delay_minutes += flight_info["pn"] * delay_minutes
                        self.seat_remains += flight_info["sn"] - flight_info["pn"]
                        if adjust_time > pas_15_time:
                            self.del_15m_flights += 1
                            if adjust_time > pas_30_time:
                                self.del_30m_flights += 1
                    if adjust_time < zero_time:
                        self.adv_flights += 1
                        self.total_adv_minutes -= timedelta_minutes(adjust_time)
                        if adjust_time < net_15_time:
                            self.adv_15m_flights += 1
                            if adjust_time < net_30_time:
                                self.adv_30m_flights += 1
                    if flight_info["tp"] != tp:
                        self.aircraft_type_conversion += 1
                    if flight_info["attr"] == "straighten":
                        self.straighten_flights += 1
                    if flight_info["attr"] == "through":
                        self.passenger_cancellation += flight_info["tpn"]
                    if flight_info["cid"] != cid:
                        self.swap_flights += 1
                    if adjust_item.departure_time.day > flight_info["dpt"].day:
                        self.make_up_flights += 1

    def statistical_cancel_info(self, solution_y: list):
        graph_node_ls = self.graph_node_ls
        for i in range(len(solution_y)):
            if solution_y[i] == 1:
                graph_node: GraphNode = graph_node_ls[i]
                flight_info = graph_node.flight_info
                self.flight_cancellation += len(flight_info["fids"])
                self.passenger_cancellation += flight_info["pn"]
        self.error_rate = (self.del_15m_flights + self.adv_15m_flights) / self.performed_flights if self.performed_flights else 0
        self.avg_del_minutes = self.total_del_minutes / self.del_flights if self.del_flights else 0
        self.avg_adv_minutes = self.total_adv_minutes / self.adv_flights if self.adv_flights else 0

    def data_picked(self):
        data = dict()
        data["IterNum"] = self.iter_num
        data["RunningTime"] = self.time_str()
        data["Scores"] = "{:.3f}".format(self.scores)
        data["PerformedFlight"] = self.performed_flights
        data["CancelledFlight"] = self.flight_cancellation
        data["StraightenFlight"] = self.straighten_flights
        data["DelFlight"] = self.del_flights
        data["AdvFlight"] = self.adv_flights
        data["TotalDelMinutes"] = "{:.1f}".format(self.total_del_minutes)
        data["TotalAdvMinutes"] = "{:.1f}".format(self.total_adv_minutes)
        data["TypeConversion"] = self.aircraft_type_conversion
        data["RotationFlight"] = self.swap_flights
        data["MakeUpFlight"] = self.make_up_flights
        data["ErrorRate"] = "{:.6f}".format(self.error_rate)
        data["PassengerCancellation"] = int(self.passenger_cancellation)
        data["PassengerDelayNums"] = int(self.passenger_delay_nums)
        data["PassengerDelayMinutes"] = self.passenger_delay_minutes
        data["SeatRemains"] = int(self.seat_remains)
        data["Del15mFlight"] = self.del_15m_flights
        data["Del30mFlight"] = self.del_30m_flights
        data["AvgDelMinutes"] = "{:.1f}".format(self.avg_del_minutes)
        data["Adv15mFlight"] = self.adv_15m_flights
        data["Adv30mFlight"] = self.adv_30m_flights
        data["AvgAdvMinutes"] = "{:.1f}".format(self.avg_adv_minutes)
        return data


class DataSaver(object):
    def __init__(self, aircraft_num: int, file_path: str):
        self.data_list = list()
        self.aircraft_num = aircraft_num
        self.file_path = file_path

    def write_csv(self):
        file_name = self.file_path + "\\" + str(self.aircraft_num) + ".csv"
        with open(file_name, mode='w', newline='') as csv_file:
            fieldnames = self.data_list[0].keys()  # 使用第一个字典的keys作为列名
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            for row in self.data_list:
                writer.writerow(row)
