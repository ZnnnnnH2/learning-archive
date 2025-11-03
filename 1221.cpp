#include <algorithm>
#include <iostream>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define ll long long

using namespace std;

/*
题目说明：
玩家有两张底牌，桌面有五张公共牌。必须使用两张底牌并从公共牌中选三张，共计五张，判断能组成的最大牌型：
- THS（同花顺）：五张同花且点数连续；
- TH（同花）：五张同花；
- SZ（顺子）：五张点数连续（忽略花色）；
- GP（高牌）：以上都不满足。
点数顺序为 2<3<…<10<J<Q<K<A，其中 A 可作最大也可作最小（A-2-3-4-5）。

实现要点概览：
- 用 shoupai / gongpai 记录底牌与公共牌在“花色×点数”网格上的出现；
- THS：对每个花色检查长度为 5 的连续段，并要求正好 2 张来自底牌、3
张来自公共牌；
- TH：某一花色若底牌有 2 张且公共牌至少 3 张，即可；
- SZ：按点数聚合（忽略花色），检查连续 5 个点数是否能由 2 张底牌 + 3
张公共牌组成；
- 通过把 A(14) 复制到索引 1 的方式，处理 A-2-3-4-5 的顺子。

注：main 中的 freopen 为本地调试用，评测时可注释掉。
*/
int Hash[200];
// shoupai / gongpai 下标：
//   第一维为花色（1..4），映射关系见 main 中 Hash：D=1, S=2, C=3, H=4；
//   第二维为点数（2..14），其中 11=J,12=Q,13=K,14=A；有时临时使用索引 1 作为 A
//   的“低位”视图（A-2-3-4-5）。
int shoupai[5][15]; // 底牌的存在标记（0/1）
int gongpai[5][15]; // 公共牌的存在标记（0/1）
// pai：一个小型计数器结构体。
// 用途 1（TH）：按花色聚合，统计该花色在底牌/公共牌中的张数。
// 用途 2（SZ）：按点数聚合（忽略花色），统计该点数是否在底牌/公共牌中出现（>0
// 即视为出现）。
struct pai {
  int shoupai;
  int gongpai;
  pai() {
    shoupai = 0;
    gongpai = 0;
  }
};

// 检查同花顺（THS）：对每个花色滑动检查长度为 5 的连续段，
// 要求正好 2 张来自底牌、3 张来自公共牌；通过把 A(14) 复制到索引 1 支持
// A-2-3-4-5。
bool check_THS() {
  for (int i = 1; i <= 4; i++) {
    shoupai[i][1] = shoupai[i][14];
    gongpai[i][1] = gongpai[i][14];
  }
  for (int i = 1; i <= 4; i++) {
    for (int j = 1; j <= 10; j++) {
      int usesShouPai = 0, useGongPai = 0;
      for (int k = 0; k <= 4; k++) {
        if (shoupai[i][j + k]) {
          usesShouPai++;
        } else if (gongpai[i][j + k]) {
          useGongPai++;
        } else {
          break;
        }
      }
      if (usesShouPai == 2 and useGongPai == 3) {
        return true;
      }
    }
  }
  for (int i = 1; i <= 4; i++) {
    shoupai[i][1] = 0;
    gongpai[i][1] = 0;
  }
  return false;
}
// 检查同花（TH）：若存在某花色满足“底牌=2 且 公共牌>=3”，即可。
bool check_TH() {
  pai p[5];
  for (int i = 1; i <= 4; i++) {
    for (int j = 2; j <= 14; j++) {
      if (shoupai[i][j]) {
        p[i].shoupai += shoupai[i][j];
      }
      if (gongpai[i][j]) {
        p[i].gongpai += gongpai[i][j];
      }
    }
  }
  for (int i = 1; i <= 4; i++) {
    if (p[i].shoupai == 2 and p[i].gongpai >= 3) {
      return true;
    }
  }
  return false;
}
// 检查顺子（SZ）：按点数聚合（忽略花色），
// 滑动窗口检查 5 连点数能否由底牌 2 张 + 公共牌 3 张恰好组成；p[1] 从 p[14]
// 复制以处理 A-2-3-4-5。
bool check_SZ() {
  pai p[20];
  for (int i = 2; i <= 14; i++) {
    for (int j = 1; j <= 4; j++) {
      if (shoupai[j][i]) {
        p[i].shoupai += shoupai[j][i];
      }
      if (gongpai[j][i]) {
        p[i].gongpai += gongpai[j][i];
      }
    }
  }
  p[1].shoupai = p[14].shoupai;
  p[1].gongpai = p[14].gongpai;
  for (int i = 1; i <= 10; i++) {
    int usesShouPai = 0, useGongPai = 0;
    for (int j = 0; j <= 4; j++) {
      if (p[i + j].shoupai) {
        usesShouPai++;
      } else if (p[i + j].gongpai) {
        useGongPai++;
      } else {
        break;
      }
    }
    if (usesShouPai == 2 and useGongPai == 3) {
      return true;
    }
  }
  return false;
}

// 读取下一个“数字或大写字母”字符（跳过空白与分隔符）。
char getc() {
  char c;
  do {
    c = getchar();
  } while ((!(c >= '0' and c <= '9')) and (!(c >= 'A' and c <= 'Z')));
  return c;
}
// 主流程：读入 n 组数据 -> 解析两张底牌与五张公共牌 -> 依优先级判断并输出结果。
int main() {
  // 本地调试重定向（评测时注释掉）：
  freopen("0000in.txt", "r", stdin);
  freopen("0000out.txt", "w", stdout);
  int n;
  scanf("%d", &n);
  // 建立点数与花色映射：'2'..'9'->2..9, '1'（十的首字符）->10,
  // J/Q/K/A->11..14； 花色：D=1, S=2, C=3, H=4（用于数组第一维）。
  Hash['A'] = 14;
  for (int i = 2; i <= 9; i++)
    Hash[i + '0'] = i;
  Hash['1'] = 10;
  Hash['J'] = 11;
  Hash['Q'] = 12;
  Hash['K'] = 13;
  Hash['H'] = 4;
  Hash['S'] = 2;
  Hash['C'] = 3;
  Hash['D'] = 1;
  while (n--) {
    memset(shoupai, 0, sizeof(shoupai));
    memset(gongpai, 0, sizeof(gongpai));
    for (int i = 1; i <= 2; i++) {
      char Hs, Ds;
      Hs = getc();
      Ds = getc();
      if (Ds == '1') {
        getc();
      }
      shoupai[Hash[Hs]][Hash[Ds]]++;
    }
    for (int i = 1; i <= 5; i++) {
      char Hs, Ds;
      Hs = getc();
      Ds = getc();
      if (Ds == '1') {
        getc();
      }
      gongpai[Hash[Hs]][Hash[Ds]]++;
    }
    if (check_THS()) {
      printf("THS\n");
    } else if (check_TH()) {
      printf("TH\n");
    } else if (check_SZ()) {
      printf("SZ\n");
    } else {
      printf("GP\n");
    }
  }
  return 0;
}
// ZnH2