| 层级 | Python 语法                   | 是否必须        | 出现在哪               |
| -- | ---------------------------    | ----------- | ------------------ |
| L0 | import / from import           | ✅ 必须        | 全部                 |
| L0 | if `__name__ == "__main__"`    | ✅ 必须        | 全部                 |
| L1 | 函数定义 `def`                  | ✅ 必须        | counter / codic    |
| L1 | 类定义 `class`                
 | ✅ 必须        | 所有                 |
| L1 | 装饰器 `@xxx`                  | ✅ 必须        | 全部                 |
| L2 | for 循环                       | ✅ 必须        | codic / fir        |
| L2 | 列表 `[]`                      | ✅ 必须        | codic / fir / case |
| L2 | 字典 `{}`                      | ✅ 必须        | codic              |
| L2 | lambda                         | ⚠️ 建议       | codic              |
| L3 | 列表推导式                       | ⚠️ 可延后      | case / codic       |
| L3 | 类型注解 `x: int`                | ❌ 可忽略       | counter            |
| L3 | 返回类（函数返回 class）           | ⚠️ PyCDE 特有 | counter            |
| L4 | 魔法属性 / monkey patch          | ❌ 不学        | case_example       |
