from models.handing import FlightData
from models.utils import AdjustItem, GraphNode, Airport, AirportClose, CloseScene
from models.utils import SlotScene, AirportSlot, Slot, SlotItem
from datetime import timedelta, datetime


def change_aircraft_para(time: datetime):
    if time <= datetime(year=2017, month=5, day=6, hour=16):
        return 15
    else:
        return 5


def model_change_para(before: int, after: int, map_ls: dict):
    if before == after:
        return 0
    else:
        return 500*map_ls[str(before)+str(after)]


def passenger_delay_para(delay_time: timedelta):
    if delay_time <= timedelta(hours=2):
        return 1
    elif delay_time <= timedelta(hours=4):
        return 1.5
    elif delay_time <= timedelta(hours=8):
        return 2
    else:
        return 3


class Graph(object):
    def __init__(self, flight_data: FlightData):
        self.flight_data = flight_data
        self.queue = []
        self.close_scene = CloseScene()
        self.typhoon_scene: dict = flight_data.typhoon_scene
        self.slot_scene: SlotScene = self.flight_data.slot_scene
        for tip_node in flight_data.aircraft_list.values():
            self.queue.append((tip_node.key, tip_node.adjust_list[timedelta(0)].adjust_time))
        self.type_change_map = {'12': 0, '13': 2, '14': 4, '21': 0.5, '23': 2, '24': 4,
                                '31': 1.5, '32': 1.5, '34': 2, '41': 1.5, '42': 1.5, '43': 2}

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
        max_lead_time: timedelta = self.flight_data.max_lead_time

        zero_time = timedelta(minutes=0)
        adjust_item_num = 0
        while self.queue:
            # print(len(self.queue), self.queue)
            current_node_num, adjust_time = self.queue.pop(0)
            current_node: GraphNode = node_list[current_node_num]
            current_flight_info: dict = current_node.flight_info
            current_adjust_info: AdjustItem = current_node.adjust_list[adjust_time]
            current_airport = current_flight_info['ap']
            current_time = current_adjust_info.arrival_time
            alter_flights: Airport = airport_list[current_airport]
            alter_flight_list = [201] if current_node_num == -24 else alter_flights.flight_list  # 处理特殊航班
            for nn in alter_flight_list:
                alter_flight_node: GraphNode = node_list[nn]
                alter_flight_info: dict = alter_flight_node.flight_info
                alter_flight_adjust: dict = alter_flight_node.adjust_list
                alter_flight_dp = alter_flight_info['dp']
                alter_flight_dpt = alter_flight_info['dpt']
                alter_flight_ap = alter_flight_info['ap']
                alter_flight_avt = alter_flight_info['avt']

                # 尝试在alter_flight_adjust中加入AdjustItem
                # if zero_time not in alter_flight_adjust.keys():
                if not alter_flight_adjust:
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

                    if is_takeoff_forbid_t or is_landing_forbid_t:
                        if is_takeoff_forbid_t:  # 起飞遭遇台风场景
                            slots: AirportSlot = self.slot_scene[alter_flight_dp][0]
                            # 尝试提前
                            takeoff_slots: Slot = slots.takeoff_slot
                            earliest_advance_time = alter_flight_dpt - max_lead_time
                            advance_slot = takeoff_slots.midst_eq(earliest_advance_time,
                                                                  self.typhoon_scene[alter_flight_dp].start_time)
                            # 尝试延误
                            # landing_slots = slots.landing_slot
                            latest_delayed_time = alter_flight_dpt + max_delay_time
                            delay_slot = takeoff_slots.midst_eq(self.typhoon_scene[alter_flight_dp].end_time,
                                                                latest_delayed_time)
                            # 将落入的slot加入node中
                            available_slot = advance_slot + delay_slot
                            if not available_slot:
                                continue
                            for s in available_slot:
                                s: SlotItem
                                adjust_time = s.start_time - alter_flight_dpt
                                adjust_info = AdjustItem(alter_flight_dpt + adjust_time,
                                                         alter_flight_avt + adjust_time, adjust_time)
                                adjust_item_num += 1
                                s.fall_in.append((current_node_num, adjust_time))
                                alter_flight_adjust[adjust_time] = adjust_info

                        if is_landing_forbid_t:  # 降落遭遇台风场景
                            slots: AirportSlot = self.slot_scene[alter_flight_ap][0]
                            landing_slots = self.slot_scene[alter_flight_ap][0].landing_slot
                            latest_delayed_time = alter_flight_avt + max_delay_time
                            landing_fallin_slot = landing_slots.midst_eq(self.typhoon_scene[alter_flight_ap].end_time,
                                                                         latest_delayed_time)
                            if not landing_fallin_slot:
                                continue
                            for s in landing_fallin_slot:
                                adjust_time = s.start_time - alter_flight_avt
                                adjust_info = AdjustItem(alter_flight_dpt + adjust_time,
                                                         alter_flight_avt + adjust_time, adjust_time)
                                adjust_item_num += 1
                                s.fall_in.append((current_node_num, adjust_time))
                                alter_flight_adjust[adjust_time] = adjust_info

                    # 机场关闭场景
                    is_takeoff_forbid_c, is_landing_forbid_c = False, False
                    if alter_flight_dp in self.close_scene.airport_list:
                        for cd in self.close_scene[alter_flight_dp]:
                            cd: AirportClose
                            is_takeoff_forbid_c = cd.is_closed(alter_flight_dpt)
                            if is_takeoff_forbid_c:
                                if is_takeoff_forbid_t:  # 如果同时处于机场关闭与台风场景，按台风场景处理
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
                    if is_takeoff_forbid_c or is_landing_forbid_c:
                        delay_time_by_t, delay_time_by_l = zero_time, zero_time
                        if is_takeoff_forbid_c:
                            delay_time_by_t = is_takeoff_forbid_c - alter_flight_dpt
                        if is_landing_forbid_c:
                            delay_time_by_l = is_landing_forbid_c - alter_flight_avt
                        if delay_time_by_t <= max_delay_time and delay_time_by_l <= max_delay_time:
                            delay_time = max(delay_time_by_t, delay_time_by_l)
                            print(
                                f'node:{nn} cid:{alter_flight_info["cid"]} fids:{alter_flight_info["fids"]}受机场关闭影响，延误{delay_time}')
                            adjust_info = AdjustItem(alter_flight_dpt + delay_time,
                                                     alter_flight_info['avt'] + delay_time, delay_time)
                            adjust_item_num += 1
                            if delay_time not in alter_flight_adjust.keys():
                                alter_flight_adjust[delay_time] = adjust_info
                        else:  # 无法通过延误避免进入关闭机场
                            continue

                    # 正常连接
                    if min_turn_time <= alter_flight_dpt - current_time:  # 可以直接连接
                        delay_time = zero_time
                    elif min_turn_time <= alter_flight_dpt - current_time + max_delay_time:  # 可以通过延误连接
                        delay_time = current_time - alter_flight_dpt + min_turn_time
                    else:  # 无法连接
                        continue

                    adjust_info = AdjustItem(alter_flight_dpt + delay_time, alter_flight_info['avt'] + delay_time,
                                             delay_time)
                    adjust_item_num += 1
                    if delay_time not in alter_flight_adjust.keys():
                        alter_flight_adjust[delay_time] = adjust_info

                # 尝试连接
                for afa in alter_flight_adjust.values():
                    afa: AdjustItem
                    if min_turn_time <= afa.departure_time - current_time:
                        if afa.adjust_time >= zero_time:
                            adjust_cost = afa.adjust_time.seconds/3600 * 100
                            passenger_cost = passenger_delay_para(afa.adjust_time) * alter_flight_info['pn']
                        else:
                            adjust_cost = -afa.adjust_time.seconds/3600 * 150
                            passenger_cost = 0

                        if current_flight_info['cid'] != alter_flight_info['cid']:
                            change_cost = change_aircraft_para(afa.departure_time)
                            change_cost += model_change_para(current_flight_info['tp'], alter_flight_info['tp'],
                                                             self.type_change_map)
                        else:
                            change_cost = 0

                        if alter_flight_info['sn'] < current_flight_info['pn']:
                            passenger_cancel_num = current_flight_info['pn'] - alter_flight_info['sn']
                            passenger_cost += passenger_cancel_num * 4

                        cost = (adjust_cost + passenger_cost + change_cost) * alter_flight_info['para']

                        if (current_node_num, adjust_time, cost) not in afa.pre:
                            afa.pre.append((current_node_num, adjust_time, cost))

                        if (nn, afa.adjust_time) not in current_adjust_info.suc:
                            current_adjust_info.suc.append((nn, afa.adjust_time))
                        if (nn, afa.adjust_time) not in self.queue:
                            self.queue.append((nn, afa.adjust_time))
        print(f'AdjustItem num: {adjust_item_num}')
