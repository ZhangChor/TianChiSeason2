from docplex.mp.model import Model


class MinPattern(object):
    def __init__(self, dual: list, demand_length: list, length: int):
        self.m_set = range(len(dual))
        self.solver = Model('find min pattern')
        self.x_list = self.solver.integer_var_list(self.m_set, name='a')
        self.solver.add_constraint(self.solver.sum(self.x_list[i] * demand_length[i] for i in self.m_set) <= length)
        self.solver.minimize(self.solver.sum(-self.x_list[i] * dual[i] for i in self.m_set))
        self.result = None

    def solve(self):
        self.result = self.solver.solve()
        if not self.result:
            self.result = self.solver.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution(self) -> list:
        return [self.result.get_value('a_' + str(s)) for s in self.m_set]

    @property
    def optimal(self) -> float:
        return self.solver.objective_value


if __name__ == '__main__':
    pattern = [[2, 0, 0],
               [0, 1, 0],
               [0, 0, 1]]  # 模式集合
    cost_of_pattern = [5, 5, 5]  # 模式对应的花费
    length_of_demand = [4, 5, 7]  # 所需木材的长度
    num_of_demand = [30, 20, 40]  # 所需木材长度的数量
    length_of_stock = [9, 14, 16]  # 已有的木材的长度
    cost_of_cut_stock = [5, 9, 10]  # 切割对应木材的花费
    dual_of_demand = [0, 0, 0]  # 需求的初始对偶值
    iter_num = 0
    while True:
        # 求解主问题
        quit_loop = False
        mp_solver = Model('cutting stock problem')
        n_set = range(len(pattern))
        m_set = range(len(length_of_demand))
        x_list = mp_solver.continuous_var_list(n_set, name='x')
        demand_ct = []
        for i in m_set:
            demand_ct.append(mp_solver.sum(x_list[j] * pattern[j][i] for j in n_set) >= num_of_demand[i])
            mp_solver.add_constraint(demand_ct[i], ctname=f'demand{i}')
        mp_solver.minimize(mp_solver.sum(x_list[j] * cost_of_pattern[j] for j in n_set))
        mp_solver.solve()
        print(mp_solver.solution)
        dual_of_demand = [dct.dual_value for dct in demand_ct]
        # 求解子问题
        print(f'------第{iter_num}次迭代------')
        for k in range(len(length_of_stock)):
            sp_k = MinPattern(dual_of_demand, length_of_demand, length_of_stock[k])
            sp_k.solve()
            reduce_cost = cost_of_cut_stock[k] + sp_k.optimal
            print('---')
            if reduce_cost < 0:
                quit_loop = True
                pattern.append(sp_k.solution)
                cost_of_pattern.append(cost_of_cut_stock[k])
                print(f'为需求{k}新增模式：{sp_k.solution}，reduce_cost={reduce_cost}')
            else:
                print(f'Reduce cost>=0，{reduce_cost}')
        iter_num += 1
        if not quit_loop:
            print(mp_solver.solution)
            break
