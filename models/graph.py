from datetime import timedelta, datetime
from pickle import dumps, loads

from models.handing import FlightData
from models.utils import AdjustItem, GraphNode, Airport, AirportClose, CloseScene
from models.utils import SlotScene, AirportSlot, Slot, SlotItem
from models.utils import timedelta_minutes


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
        self.graph_node_list = flight_data.graph_node_list
        self.queue = list()
        self.edge_num = 0
        self.close_scene = CloseScene()
        self.typhoon_scene: dict = flight_data.typhoon_scene
        self.slot_scene: SlotScene = flight_data.slot_scene
        self.turn_time: dict = flight_data.turn_time
        self.advance_flight_node_nums = flight_data.mutex_flight_node_nums
        for tip_node in flight_data.aircraft_list.values():
            self.queue.append((tip_node.adjust_list[timedelta(0)].departure_time, tip_node.key,
                               tip_node.adjust_list[timedelta(0)].adjust_time))
        self.type_change_map = {'12': 0, '13': 2, '14': 4, '21': 0.5, '23': 2, '24': 4,
                                '31': 1.5, '32': 1.5, '34': 2, '41': 1.5, '42': 1.5, '43': 2}

    def add_close(self, closed_list: list):
        for closed in closed_list:
            airport_num, close_time, open_time, effective_date, expiration_date = closed
            airport_closed = AirportClose(airport_num, close_time, open_time, effective_date, expiration_date)
            self.close_scene.add_scene(airport_num, airport_closed)

    def build_graph_v2(self):
        node_list: dict = self.flight_data.graph_node_list
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
            dpt, current_node_num, current_adjust_time = current_mark
            current_node: GraphNode = node_list[current_node_num]
            current_flight_info: dict = current_node.flight_info
            current_adjust_item: AdjustItem = current_node.adjust_list[current_adjust_time]
            current_airport = current_flight_info['ap']
            current_time = current_adjust_item.arrival_time
            alter_flights: Airport = airport_list[current_airport]
            landing_fid = current_flight_info['fids'][-1]
            alter_flight_list = [201] if current_node_num == -24 else alter_flights.departure_flight_list  # 处理特殊航班
            for alter_node_num in alter_flight_list:
                alter_flight_node: GraphNode = node_list[alter_node_num]
                alter_flight_info: dict = alter_flight_node.flight_info
                alter_adjust_list: dict = alter_flight_node.adjust_list
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

                # 处理后续航班的调整方案
                if alter_flight_info['attr'] == "straighten":
                    # 依次判断并连接
                    self._trying_connect(alter_node_num, alter_flight_node, turn_time, current_time, current_node_num,
                                         current_adjust_item, endorsement_num)
                else:
                    if alter_flight_info['tmk']:
                        # 依次判断并连接
                        self._trying_connect(alter_node_num, alter_flight_node, turn_time, current_time,
                                             current_node_num, current_adjust_item, endorsement_num)
                    else:
                        # 判断是否受台风影响
                        max_delay_time = max_domestic_delay if alter_flight_info['dom'] == '国内' else max_foreign_delay
                        if alter_flight_dp in self.typhoon_scene.keys():
                            is_takeoff_forbid_t = self.typhoon_scene[alter_flight_dp].takeoff_forbid(alter_flight_dpt)
                        else:
                            is_takeoff_forbid_t = False
                        if alter_flight_ap in self.typhoon_scene.keys():
                            is_landing_forbid_t = self.typhoon_scene[alter_flight_ap].landing_forbid(alter_flight_avt)
                        else:
                            is_landing_forbid_t = False
                        if not alter_adjust_list and (is_takeoff_forbid_t or is_landing_forbid_t):
                            # 生成方案，依次判断并连接
                            alter_flight_info['tmk'] = True
                            self._typhoon_scene_adj(is_takeoff_forbid_t, is_landing_forbid_t, alter_node_num,
                                                    alter_flight_dp, alter_flight_dpt, alter_flight_ap,
                                                    alter_flight_avt, current_node_num, max_lead_time, max_delay_time)
                            self._closed_scene_adj(is_takeoff_forbid_t, is_landing_forbid_t, alter_flight_dp,
                                                   alter_flight_dpt, alter_flight_ap, alter_flight_avt, alter_node_num,
                                                   max_delay_time)
                            self._trying_connect(alter_node_num, alter_flight_node, turn_time, current_time,
                                                 current_node_num, current_adjust_item, endorsement_num)
                        else:
                            # 计算最小延误，根据调整时间判断是否已经计算过
                            self._closed_scene_adj(is_takeoff_forbid_t, is_landing_forbid_t, alter_flight_dp,
                                                   alter_flight_dpt, alter_flight_ap, alter_flight_avt, alter_node_num,
                                                   max_delay_time)
                            self._calcul_min_delay(current_time, alter_flight_dpt, turn_time, max_delay_time,
                                                   alter_node_num, current_node_num, current_adjust_item,
                                                   endorsement_num)
                # 尝试连接目的机场
                if current_airport in self.flight_data.airport_stop_tp.keys():
                    destination_airport = self.flight_data.get_arrival_airport_graph_node(current_airport)
                    destination_mark = (destination_airport.key, zero_time)
                    if destination_mark not in current_adjust_item.suc:
                        current_adjust_item.suc.append(destination_mark)
                    current_mark_pre = (current_node_num, current_adjust_time, 0)
                    if current_mark_pre not in destination_airport.adjust_list[zero_time].pre:
                        destination_airport.adjust_list[zero_time].pre.append(current_mark_pre)
        print(f'AdjustItem num: {self.flight_data.adjust_item_cnt}')
        print(f'Edge num: {self.edge_num}')

    def _trying_connect(self, alter_node_num: int, alter_flight_node: GraphNode, turn_time: timedelta,
                        current_time: datetime, current_node_num: int, current_adjust_item: AdjustItem,
                        endorsement_num: int):
        alter_adjust_list = alter_flight_node.adjust_list
        alter_flight_info = alter_flight_node.flight_info
        current_node = self.graph_node_list[current_node_num]
        current_flight_info = current_node.flight_info
        for afa in alter_adjust_list.values():
            afa: AdjustItem
            if turn_time <= afa.departure_time - current_time or \
                    (current_flight_info['cid'] == alter_flight_info['cid'] and
                     timedelta(minutes=40) <= afa.departure_time - current_time):
                if current_node_num not in alter_flight_node.pres:
                    alter_flight_node.pres.add(current_node_num)
                    for pre in current_node.pres:
                        alter_flight_node.pres.add(pre)
                self._calcul_cost(afa, current_node_num, current_adjust_item, alter_node_num, endorsement_num)

    def _calcul_cost(self, afa: AdjustItem, current_node_num: int, current_adjust_item: AdjustItem,
                     alter_node_num: int, endorsement_num: int):
        zero_time = timedelta(minutes=0)
        current_node = self.graph_node_list[current_node_num]
        current_flight_info = current_node.flight_info
        alter_flight_info = self.graph_node_list[alter_node_num].flight_info
        if afa.adjust_time > zero_time:  # 延误
            adjust_cost = afa.adjust_time.seconds / 3600 * 100
            passenger_cost = passenger_delay_para(afa.adjust_time) * alter_flight_info['pn']
            endorsement_cost = passenger_endorse_delay_para(afa.adjust_time) * endorsement_num
        else:  # 提前
            adjust_cost = -timedelta_minutes(afa.adjust_time) / 60 * 150
            passenger_cost = 0
            endorsement_cost = 0
        change_cost = model_change_para(current_flight_info['tp'], alter_flight_info['tp'], self.type_change_map)

        if alter_flight_info['sn'] < current_flight_info['pn'] and current_flight_info['attr'] != 'through':  # 取消旅客
            passenger_cancel_num = current_flight_info['pn'] - alter_flight_info['sn']
            passenger_cost += passenger_cancel_num * 4

        cost = (adjust_cost + passenger_cost + change_cost + endorsement_cost) * alter_flight_info['para']
        cost += afa.cost
        edge_mark = (current_node_num, current_adjust_item.adjust_time, cost)
        if edge_mark not in afa.pre:
            afa.pre.append(edge_mark)
            self.edge_num += 1
        if (alter_node_num, afa.adjust_time) not in current_adjust_item.suc:
            current_adjust_item.suc.append((alter_node_num, afa.adjust_time))
        if (alter_flight_info["dpt"], alter_node_num, afa.adjust_time) not in self.queue:
            self.queue.append((alter_flight_info["dpt"], alter_node_num, afa.adjust_time))
        # print(f"{edge_mark}->{(alter_node_num, afa.adjust_time)}")

    def _typhoon_scene_adj(self, is_takeoff_forbid_t: bool, is_landing_forbid_t: bool, alter_node_num: int,
                           alter_flight_dp: int, alter_flight_dpt: datetime, alter_flight_ap: int,
                           alter_flight_avt: datetime, current_node_num: int, max_lead_time: timedelta,
                           max_delay_time: timedelta):
        alter_adjust_list = self.graph_node_list[alter_node_num].adjust_list
        if is_takeoff_forbid_t:  # 起飞遭遇台风场景
            slots: AirportSlot = self.slot_scene[alter_flight_dp][0]
            # 尝试提前
            takeoff_slots: Slot = slots.takeoff_slot
            earliest_advance_time = alter_flight_dpt - max_lead_time
            advance_slot = takeoff_slots.midst_eq(earliest_advance_time,
                                                  self.typhoon_scene[alter_flight_dp].start_time)
            if advance_slot:
                self.advance_flight_node_nums.add(alter_node_num)
            # 尝试延误
            # landing_slots = slots.landing_slot
            latest_delayed_time = alter_flight_dpt + max_delay_time
            delay_slot = takeoff_slots.midst_eq(self.typhoon_scene[alter_flight_dp].end_time,
                                                latest_delayed_time)
            # 将落入的slot加入node中
            available_slot = advance_slot + delay_slot
            for s in available_slot:
                s: SlotItem
                adjust_time = s.start_time - alter_flight_dpt
                adjust_item = AdjustItem(alter_node_num, alter_flight_dpt + adjust_time,
                                         alter_flight_avt + adjust_time, adjust_time)
                self.flight_data.adjust_item_cnt += 1
                s.fall_in.append((current_node_num, adjust_time))
                alter_adjust_list[adjust_time] = adjust_item

        if is_landing_forbid_t:  # 降落遭遇台风场景
            slots: AirportSlot = self.slot_scene[alter_flight_ap][0]
            landing_slots = slots.landing_slot
            latest_delayed_time = alter_flight_avt + max_delay_time
            landing_fallin_slot = landing_slots.midst_eq(self.typhoon_scene[alter_flight_ap].end_time,
                                                         latest_delayed_time)
            for s in landing_fallin_slot:
                adjust_time = s.start_time - alter_flight_avt
                adjust_item = AdjustItem(alter_node_num, alter_flight_dpt + adjust_time,
                                         alter_flight_avt + adjust_time, adjust_time)
                self.flight_data.adjust_item_cnt += 1
                s.fall_in.append((current_node_num, adjust_time))
                alter_adjust_list[adjust_time] = adjust_item

    def _closed_scene_adj(self, is_takeoff_forbid_t: bool, is_landing_forbid_t: bool, alter_flight_dp: int,
                          alter_flight_dpt: datetime, alter_flight_ap: int, alter_flight_avt: datetime,
                          alter_node_num: int, max_delay_time: timedelta):
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
            zero_time = timedelta(minutes=0)
            alter_node: GraphNode = self.graph_node_list[alter_node_num]
            alter_flight_info = alter_node.flight_info
            alter_adjust_list = alter_node.adjust_list

            delay_time_by_takeoff, delay_time_by_landing = zero_time, zero_time
            if is_takeoff_forbid_c:
                delay_time_by_takeoff = opening_time_by_takeoff - alter_flight_dpt
            if is_landing_forbid_c:
                delay_time_by_landing = opening_time_by_landing - alter_flight_avt
            if delay_time_by_takeoff <= max_delay_time and delay_time_by_landing <= max_delay_time:
                delay_time = max(delay_time_by_takeoff, delay_time_by_landing)
                # print(
                #     f'node:{alter_node_num} cid:{alter_flight_info["cid"]} fids:{alter_flight_info["fids"]}受机场关闭影响，延误{delay_time}')
                adjust_item = AdjustItem(alter_node_num, alter_flight_dpt + delay_time,
                                         alter_flight_info['avt'] + delay_time, delay_time)
                self.flight_data.adjust_item_cnt += 1
                if delay_time not in alter_adjust_list.keys():
                    alter_adjust_list[delay_time] = adjust_item

    def _calcul_min_delay(self, current_time: datetime, alter_flight_dpt: datetime, turn_time: timedelta,
                          max_delay_time: timedelta, alter_node_num: int, current_node_num: int,
                          current_adjust_item: AdjustItem, endorsement_num: int):
        # 将最大延误时间设定的越高，图越大，运算时间越长，但解的效果不一定明显提升，这里设置为6小时，避免图无限的增大
        max_delay_time = timedelta(hours=4)
        alter_node: GraphNode = self.graph_node_list[alter_node_num]
        alter_flight_info = alter_node.flight_info
        current_node: GraphNode = self.graph_node_list[current_node_num]
        current_flight_info = current_node.flight_info
        if turn_time <= alter_flight_dpt - current_time or \
                (current_flight_info['cid'] == alter_flight_info['cid'] and
                 timedelta(minutes=40) <= alter_flight_dpt - current_time):  # 可以直接连接
            delay_time = timedelta(minutes=0)
        elif turn_time <= alter_flight_dpt - current_time + max_delay_time:  # 可以通过延误连接
            delay_time = current_time - alter_flight_dpt + turn_time
        else:  # 无法连接
            return

        alter_adjust_list = alter_node.adjust_list
        if delay_time in alter_adjust_list.keys():
            self._calcul_cost(alter_adjust_list[delay_time], current_node_num, current_adjust_item, alter_node_num,
                              endorsement_num)
            return
        adjust_item = AdjustItem(alter_node_num, alter_flight_dpt + delay_time,
                                 alter_flight_info['avt'] + delay_time, delay_time)
        self.flight_data.adjust_item_cnt += 1
        alter_adjust_list[delay_time] = adjust_item
        if len(alter_adjust_list) > 1 and alter_node_num >= 0:
            self.flight_data.mutex_flight_node_nums.add(alter_node_num)
        self._calcul_cost(adjust_item, current_node_num, current_adjust_item, alter_node_num, endorsement_num)

    def save_graph_node_list(self):
        file_path = self.flight_data.workspace_path + '/tmp'
        file_name = "/graph_node_list" + str(self.flight_data.aircraft_volume) + '.pkl'
        bt = dumps(self.graph_node_list)
        with open(file_path + file_name, "wb") as file:
            file.write(bt)
