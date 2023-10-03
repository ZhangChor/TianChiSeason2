#!/home/zc/miniconda3/envs/cplex_acd/bin/python
import sys

sys.path.append(r'/home/zc/PathModel3')
from docplex.mp.model import Model


class MasterProblemSolver(object):
    def __init__(self, route: list, cost: list, var_num_list: list, cancel: list, slot_used: list, slot_capacity: list,
                 parking_used: list, parking_capacity: list, relaxation=True):
        self._flight_node_num = len(cancel)
        self._aircraft_num = len(var_num_list)
        self._route_num = sum(var_num_list)
        self._slot_num = len(slot_capacity)
        self._parking_num = len(parking_capacity)
        self._var_name_list_x = []
        self.result = None

        j = 0
        for n in var_num_list:
            for i in range(n):
                self._var_name_list_x.append(f'c{j}r{i}')
            j += 1
        self._var_name_list_y = [f'n{i}' for i in range(self._flight_node_num)]
        self._solver = Model(name="route assignment problem")
        if relaxation:
            self._x_list = self._solver.continuous_var_list(self._var_name_list_x, name='x', ub=1)
        else:
            self._x_list = self._solver.binary_var_list(self._var_name_list_x, name='x')
        self._y_list = self._solver.continuous_var_list(self._var_name_list_y, name='y', ub=1)
        # 航班约束：每次航班最多仅能被选入解一次
        for j in range(self._flight_node_num):
            flight_ct = self._solver.sum(route[i][j] * self._x_list[i]
                                         for i in range(self._route_num)) + self._y_list[j] == 1
            self._solver.add_constraint(flight_ct, ctname=f'flight_node{j}')
        start = 0
        cid = 0
        # 飞机约束：每架飞机有一条路径
        for n in var_num_list:
            aircraft_ct = self._solver.sum(self._x_list[i] for i in range(start, start + n)) <= 1
            self._solver.add_constraint(aircraft_ct, ctname=f'aircraft{cid}')
            start += n
            cid += 1
        # slot容量限制
        for j in range(self._slot_num):
            self._solver.add_constraint(self._solver.sum(slot_used[i][j] * self._x_list[i]
                                                         for i in range(self._route_num)) <= slot_capacity[j],
                                        ctname=f'slot{j}')
        # 机场容量限制
        for j in range(self._parking_num):
            self._solver.add_constraint(self._solver.sum(parking_used[i][j] * self._x_list[i]
                                                         for i in range(self._route_num)) <= parking_capacity[j],
                                        ctname=f'parking{j}')
        # 目标函数
        self._solver.minimize(self._solver.sum(cost[i] * self._x_list[i] for i in range(self._route_num)) +
                              self._solver.sum(cancel[j] * self._y_list[j] for j in range(self._flight_node_num)))

    def add_fix_int_var(self, solution_x: list):
        for i in range(len(solution_x)):
            if solution_x[i] == 1:
                self._solver.add_constraint(self._x_list[i] == 1)

    def print_info(self):
        for j in range(self._flight_node_num):
            print(self._solver.get_constraint_by_name('flight_node%s' % j))
        for cid in range(self._aircraft_num):
            print(self._solver.get_constraint_by_name('aircraft%s' % cid))
        # 输出目标函数
        print("Objective:")
        print(self._solver.get_objective_expr())
        self._solver.print_information()  # 输出模型信息

    def solve(self):
        self.result = self._solver.solve()
        if not self.result:
            self.result = self._solver.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution_x(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_name_list_x]

    @property
    def solution_y(self) -> list:
        return [self.result.get_value('y_' + s) for s in self._var_name_list_y]

    @property
    def flight_node_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('flight_node'))

    @property
    def aircraft_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('aircraft'))

    @property
    def slot_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('slot'))

    @property
    def parking_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('parking'))

    @property
    def optimal(self) -> float:
        return self._solver.objective_value


class ShortestPath(object):
    def __init__(self, ass_matrix: list[list], node_attr: list, edge_cost: list, relaxation=True):
        self.node_num = len(node_attr)  # number of node
        self.edge_num = len(edge_cost)  # number of edge
        self._var_name_list = [f'e{j}' for j in range(self.edge_num)]
        self.sp = Model(name="shortest path problem")
        if relaxation:
            self.var_list = self.sp.continuous_var_list(self._var_name_list, name='x')
        else:
            self.var_list = self.sp.binary_var_list(self._var_name_list, name='x')
        for i in range(self.node_num):
            row = ass_matrix[i]
            self.sp.add_constraint(self.sp.sum(row[j] * self.var_list[j] for j in range(self.edge_num)) == node_attr[i],
                                   ctname=f'node{i}')
        self.sp.minimize(self.sp.sum(edge_cost[j] * self.var_list[j] for j in range(self.edge_num)))
        self.result = None

    def add_mutex_constraint(self, mutex_graph_node_edges: dict):
        k = 0
        for graph_node_num, edges in mutex_graph_node_edges.items():
            node_ct = [0] * self.edge_num
            for i in edges:
                node_ct[i] = 1
            self.sp.add_constraint(self.sp.sum(node_ct[j] * self.var_list[j] for j in range(self.edge_num)) <= 1,
                                   ctname=f'mut_flight{k}')
            k += 1

    def print_info(self):
        for j in range(self.node_num):
            print(self.sp.get_constraint_by_name('node%s' % j))

        # 输出目标函数
        print("Objective:")
        print(self.sp.get_objective_expr())
        self.sp.print_information()  # 输出模型信息

    def solve(self):
        self.result = self.sp.solve()
        if not self.result:
            self.result = self.sp.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    def is_int(self) -> bool:
        for i in self.solution:
            if i != int(i):
                return False
        return True

    @property
    def solution(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_name_list]

    @property
    def optimal(self) -> float:
        return self.sp.objective_value


class MultiFlowModel(object):
    def __init__(self, ass_matrix: list[list], flow_ct: list, edge_cost: list, cancel_cost: list):
        self.node_num = len(flow_ct)  # number of node
        self.edge_num = len(edge_cost)  # number of edge
        self.cancel_num = len(cancel_cost)
        self._var_x_name_list = [f'e{j}' for j in range(self.edge_num)]
        self._var_y_name_list = [f'n{i}' for i in range(self.cancel_num)]
        self.mfp = Model(name="multi flow model problem")
        self.var_x_list = self.mfp.continuous_var_list(self._var_x_name_list, name='x')
        self.var_y_list = self.mfp.continuous_var_list(self._var_y_name_list, name='y', ub=1)
        # 流平衡约束
        for i in range(self.node_num):
            row = ass_matrix[i]
            self.mfp.add_constraint(
                self.mfp.sum(row[j] * self.var_x_list[j] for j in range(self.edge_num)) == flow_ct[i],
                ctname=f'node{i}')
        # 取消成本
        for i in range(self.cancel_num):
            row = ass_matrix[i]
            ads_row = list(map(lambda x: abs(x), row))
            if (not list_ge(row, [0]*self.edge_num)) and (not list_le(row, [0]*self.edge_num)):
                self.mfp.add_constraint(self.mfp.sum(ads_row[j] * self.var_x_list[j] for j in range(self.edge_num)) +
                                        self.var_y_list[i] * 2 == 2, ctname=f'cancel_node{i}')
        self.mfp.minimize(self.mfp.sum(edge_cost[j] * self.var_x_list[j] for j in range(self.edge_num)) +
                          self.mfp.sum(cancel_cost[j] * self.var_y_list[j] for j in range(len(cancel_cost))))
        self.result = None

    def add_mutex_constraint(self, mutex_graph_node_edges: dict):
        # 顶点互斥约束
        k = 0
        for graph_node_num, edges in mutex_graph_node_edges.items():
            node_ct = [0] * self.edge_num
            for i in edges:
                node_ct[i] = 1
            self.mfp.add_constraint(self.mfp.sum(node_ct[j] * self.var_x_list[j] for j in range(self.edge_num)) <= 1,
                                    ctname=f'mut_flight{k}')
            k += 1

    def print_info(self):
        for j in range(self.node_num):
            print(self.mfp.get_constraint_by_name('node%s' % j))
        for j in range(self.cancel_num):
            print(self.mfp.get_constraint_by_name('cancel_node%s' % j))

        # 输出目标函数
        print("Objective:")
        print(self.mfp.get_objective_expr())
        self.mfp.print_information()  # 输出模型信息

    def solve(self):
        self.result = self.mfp.solve()
        if not self.result:
            self.result = self.mfp.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution_x(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_x_name_list]

    @property
    def solution_y(self) -> list:
        return [self.result.get_value('y_' + s) for s in self._var_y_name_list]

    @property
    def optimal(self) -> float:
        return self.mfp.objective_value


def list_le(lista: list, listb: list):
    return all(a <= b for a, b in zip(lista, listb))


def list_ge(lista: list, listb: list):
    return all(a >= b for a, b in zip(lista, listb))


if __name__ == "__main__":
    # %%
    # A = [[1, 1, 1, 0, 0, 0],
    #      [-1, 0, 0, 1, 0, 0],
    #      [0, -1, 0, 0, 1, 0],
    #      [0, 0, -1, -1, 0, 1],
    #      [0, 0, 0, 0, -1, -1]]
    # b = [2, 0, 0, 0, -2]
    # c = [2, 1, -3, 0, 2, 2]
    # d = [2, 2, 2]
    # sl = MultiFlowModel(A, b, c, d)
    # sl.print_info()
    # sl.solve()
    # print(sl.optimal)
    # print(sl.solution_x)
    # print(sl.solution_y)
    # %%
    A = [[1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
         [0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
         [-1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
         [0, -1, -1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
         [0, 0, 0, -1, 1, 0, 1, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0],
         [0, 0, 0, 0, -1, 1, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0],
         [0, 0, 0, 0, 0, 0, 0, -1, 0, 1, 1, 0, 0, 0, 0, 0, 0],
         [0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0],
         [0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, -1, 1, 1, 0, 0, 0],
         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 1, 1, 0],
         [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 1],
         [0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
         [0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1]]
    b = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, -1]
    c = [0, 2, 0, 0, 2, 4, 2, 0, 0, 0, 2, 1, 0, 1, 0, 2, 3]
    d = [0, 0, 2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0]
    sl = MultiFlowModel(A, b, c, d)
    # sl.print_info()
    sl.solve()
    print(sl.optimal)
    print(sl.solution_x)
    print(sl.solution_y)
