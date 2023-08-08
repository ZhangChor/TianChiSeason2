from datetime import timedelta, datetime

from models.handing import FlightData
from models.utils import AdjustItem, GraphNode, Airport, AirportClose, CloseScene
from models.utils import SlotScene, AirportSlot, Slot, SlotItem
from models.utils import timedelta_minutes


def change_aircraft_para(time: datetime):
    if time <= datetime(year=2017, month=5, day=6, hour=16):
        return 15
    else:
        return 5


def model_change_para(before: int, after: int, map_ls: dict):
    if before == after:
        return 0
    else:
        return 500 * map_ls[str(before) + str(after)]


def passenger_delay_para(delay_time: timedelta):
    if delay_time <= timedelta(hours=2):
        return 1
    elif delay_time <= timedelta(hours=4):
        return 1.5
    elif delay_time <= timedelta(hours=8):
        return 2
    else:
        return 3


def passenger_endorse_delay_para(delay_time: timedelta):
    if delay_time < timedelta(hours=6):
        return delay_time.seconds / (3600 * 30)
    elif delay_time < timedelta(hours=12):
        return delay_time.seconds / (3600 * 24)
    elif delay_time < timedelta(hours=24):
        return delay_time.seconds / (3600 * 24)
    elif delay_time < timedelta(hours=36):
        return delay_time.seconds / (3600 * 18)
    elif delay_time <= timedelta(hours=48):
        return delay_time.seconds / (3600 * 16)
    else:
        return 4


class Graph(object):
    def __init__(self, flight_data: FlightData):
        self.flight_data = flight_data
        self.queue = []
        self.close_scene = CloseScene()
        self.typhoon_scene: dict = flight_data.typhoon_scene
        self.slot_scene: SlotScene = flight_data.slot_scene
        self.turn_time: dict = flight_data.turn_time
        self.advance_flight_node_nums = flight_data.advance_flight_node_nums
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
        edge_num = 0
        while self.queue:
            # print(len(self.queue), self.queue)
            current_mark = self.queue.pop(0)
            current_node_num, current_adjust_time = current_mark
            current_node: GraphNode = node_list[current_node_num]
            current_flight_info: dict = current_node.flight_info
            current_adjust_info: AdjustItem = current_node.adjust_list[current_adjust_time]
            current_airport = current_flight_info['ap']
            current_time = current_adjust_info.arrival_time
            alter_flights: Airport = airport_list[current_airport]
            landing_fid = current_flight_info['fids'][-1]
            alter_flight_list = [201] if current_node_num == -24 else alter_flights.departure_flight_list  # 处理特殊航班
            for nn in alter_flight_list:
                alter_flight_node: GraphNode = node_list[nn]
                alter_flight_info: dict = alter_flight_node.flight_info
                alter_flight_adjust: dict = alter_flight_node.adjust_list
                takeoff_fid = alter_flight_info['fids'][0]
                alter_flight_dp = alter_flight_info['dp']
                alter_flight_dpt = alter_flight_info['dpt']
                alter_flight_ap = alter_flight_info['ap']
                alter_flight_avt = alter_flight_info['avt']

                fids_key = str(landing_fid) + '-' + str(takeoff_fid)
                if fids_key in self.turn_time.keys():
                    turn_time_minute, endorsement_num = self.turn_time[fids_key]
                    turn_time = timedelta(minutes=int(turn_time_minute))
                else:
                    turn_time, endorsement_num = min_turn_time, 0

                # 尝试在alter_flight_adjust中加入AdjustItem
                # if zero_time not in alter_flight_adjust.keys():
                if not alter_flight_adjust:
                    max_delay_time = max_domestic_delay if alter_flight_info['dom'] == '国内' else max_foreign_delay

                    # 台风场景
                    if alter_flight_dp in self.typhoon_scene.keys():
                        is_takeoff_forbid_t = self.typhoon_scene[alter_flight_dp].takeoff_forbid(alter_flight_dpt)
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
                            if advance_slot:
                                self.advance_flight_node_nums.add(nn)
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
                                adjust_info = AdjustItem(nn, alter_flight_dpt + adjust_time,
                                                         alter_flight_avt + adjust_time, adjust_time)
                                self.flight_data.adjust_item_cnt += 1
                                s.fall_in.append((current_node_num, adjust_time))
                                alter_flight_adjust[adjust_time] = adjust_info

                        if is_landing_forbid_t:  # 降落遭遇台风场景
                            slots: AirportSlot = self.slot_scene[alter_flight_ap][0]
                            landing_slots = slots.landing_slot
                            latest_delayed_time = alter_flight_avt + max_delay_time
                            landing_fallin_slot = landing_slots.midst_eq(self.typhoon_scene[alter_flight_ap].end_time,
                                                                         latest_delayed_time)
                            if not landing_fallin_slot:
                                continue
                            for s in landing_fallin_slot:
                                adjust_time = s.start_time - alter_flight_avt
                                adjust_info = AdjustItem(nn, alter_flight_dpt + adjust_time,
                                                         alter_flight_avt + adjust_time, adjust_time)
                                self.flight_data.adjust_item_cnt += 1
                                s.fall_in.append((current_node_num, adjust_time))
                                alter_flight_adjust[adjust_time] = adjust_info

                    # 机场关闭场景
                    is_takeoff_forbid_c, is_landing_forbid_c = False, False
                    if alter_flight_dp in self.close_scene.airport_list:
                        for cd in self.close_scene[alter_flight_dp]:
                            cd: AirportClose
                            is_takeoff_forbid_c = cd.is_closed(alter_flight_dpt)
                            if is_takeoff_forbid_c:
                                opening_time_by_takeoff = cd.opening_time(alter_flight_dpt)
                                if is_takeoff_forbid_t:  # 如果同时处于机场关闭与台风场景，按台风场景处理
                                    is_takeoff_forbid_c = False
                                break
                    if alter_flight_ap in self.close_scene.airport_list:
                        for cd in self.close_scene[alter_flight_ap]:
                            cd: AirportClose
                            is_landing_forbid_c = cd.is_closed(alter_flight_avt)
                            if is_landing_forbid_c:
                                opening_time_by_landing = cd.opening_time(alter_flight_avt)
                                if is_landing_forbid_t:
                                    is_landing_forbid_c = False
                                break
                    if is_takeoff_forbid_c or is_landing_forbid_c:
                        delay_time_by_takeoff, delay_time_by_landing = zero_time, zero_time
                        if is_takeoff_forbid_c:
                            delay_time_by_takeoff = opening_time_by_takeoff - alter_flight_dpt
                        if is_landing_forbid_c:
                            delay_time_by_landing = opening_time_by_landing - alter_flight_avt
                        if delay_time_by_takeoff <= max_delay_time and delay_time_by_landing <= max_delay_time:
                            delay_time = max(delay_time_by_takeoff, delay_time_by_landing)
                            print(
                                f'node:{nn} cid:{alter_flight_info["cid"]} fids:{alter_flight_info["fids"]}受机场关闭影响，延误{delay_time}')
                            adjust_info = AdjustItem(nn, alter_flight_dpt + delay_time,
                                                     alter_flight_info['avt'] + delay_time, delay_time)
                            self.flight_data.adjust_item_cnt += 1
                            if delay_time not in alter_flight_adjust.keys():
                                alter_flight_adjust[delay_time] = adjust_info
                        else:  # 无法通过延误避免进入关闭机场
                            continue

                    # 正常连接
                    # 延误后，可能中间机场又受台风影响了？该数据中没有出现这种情况，不再处理!
                    forbid_list = [is_landing_forbid_c, is_takeoff_forbid_c, is_landing_forbid_t, is_takeoff_forbid_t]
                    if not sum(forbid_list):
                        if turn_time <= alter_flight_dpt - current_time:  # 可以直接连接
                            delay_time = zero_time
                        elif turn_time <= alter_flight_dpt - current_time + max_delay_time:  # 可以通过延误连接
                            delay_time = current_time - alter_flight_dpt + turn_time
                        else:  # 无法连接
                            continue

                        # if alter_flight_info['attr'] == 'through':
                        #     mid_airport: models.utils.MidstAirport = alter_flight_info['ma']
                        #     if mid_airport.airport in self.typhoon_scene.keys():
                        #         typhoon = self.typhoon_scene[mid_airport.airport]
                        #         landing_forbid = typhoon.landing_forbid(mid_airport.arrival_time+delay_time)
                        #         takeoff_forbid = typhoon.takeoff_forbid(mid_airport.departure_time+delay_time)
                        #         if landing_forbid:
                        #             print(f'num={adjust_item_num},fid={alter_flight_info["fids"]}禁止降落 {delay_time}')
                        #         if takeoff_forbid:
                        #             print(f'num={adjust_item_num},fid={alter_flight_info["fids"]}禁止起飞 {delay_time}')

                        adjust_info = AdjustItem(nn, alter_flight_dpt + delay_time,
                                                 alter_flight_info['avt'] + delay_time, delay_time)
                        self.flight_data.adjust_item_cnt += 1
                        if delay_time not in alter_flight_adjust.keys():
                            alter_flight_adjust[delay_time] = adjust_info
                # 尝试连接

                for afa in alter_flight_adjust.values():
                    afa: AdjustItem
                    if turn_time <= afa.departure_time - current_time:
                        # if nn in current_node.pres:
                        #     print(f'出现了环...{nn}')
                        if current_node_num not in alter_flight_node.pres:
                            alter_flight_node.pres.add(current_node_num)
                            for pre in current_node.pres:
                                alter_flight_node.pres.add(pre)
                        if afa.adjust_time > zero_time:  # 延误
                            adjust_cost = afa.adjust_time.seconds / 3600 * 100
                            passenger_cost = passenger_delay_para(afa.adjust_time) * alter_flight_info['pn']
                            endorsement_cost = passenger_endorse_delay_para(afa.adjust_time) * endorsement_num
                        else:  # 提前
                            adjust_cost = -timedelta_minutes(afa.adjust_time) / 60 * 150
                            passenger_cost = 0
                            endorsement_cost = 0

                        change_cost = change_aircraft_para(afa.departure_time) if current_flight_info['cid'] != \
                                                                                  alter_flight_info['cid'] else 0
                        change_cost += model_change_para(current_flight_info['tp'], alter_flight_info['tp'],
                                                         self.type_change_map)

                        if alter_flight_info['sn'] < current_flight_info['pn']:  # 取消旅客
                            passenger_cancel_num = current_flight_info['pn'] - alter_flight_info['sn']
                            passenger_cost += passenger_cancel_num * 4

                        cost = (adjust_cost + passenger_cost + change_cost + endorsement_cost) * alter_flight_info[
                            'para']
                        cost += afa.cost
                        edge_mark = (current_node_num, current_adjust_info.adjust_time, cost)
                        if edge_mark not in afa.pre:
                            afa.pre.append(edge_mark)
                        edge_num += 1
                        if (nn, afa.adjust_time) not in current_adjust_info.suc:
                            current_adjust_info.suc.append((nn, afa.adjust_time))
                        if (nn, afa.adjust_time) not in self.queue:
                            self.queue.append((nn, afa.adjust_time))
            # 尝试连接目的机场
            if current_airport in self.flight_data.airport_stop_tp.keys():
                destination_airport = self.flight_data.get_arrival_airport_graph_node(current_airport)
                destination_mark = (destination_airport.key, zero_time)
                if destination_mark not in current_adjust_info.suc:
                    current_adjust_info.suc.append(destination_mark)
                current_mark_pre = (current_node_num, current_adjust_time, 0)
                if current_mark_pre not in destination_airport.adjust_list[zero_time].pre:
                    destination_airport.adjust_list[zero_time].pre.append(current_mark_pre)

        print(f'AdjustItem num: {self.flight_data.adjust_item_cnt}')
        print(f'Edge num: {edge_num}')
