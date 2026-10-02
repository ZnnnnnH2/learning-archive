#include <iostream>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <algorithm>
#include <vector>
#include <time.h>
#include <queue>
#include <Windows.h>

typedef long long ll;
typedef int *intt;
typedef char *charr;

using namespace std;
const int inf = 0x3f3f3f3f;
const int N = 1e5 + 5;
bool check(int x)
{
    if (x >= 10)
        return false;
    return true;
}
int main()
{
    srand(time(0));
    const int NUMOFMATH = 30;
    const int mod1 = 100;
    const int mod2 = 9;
    FILE *fp = fopen("dividemath.doc", "w");
    FILE *fp2 = fopen("divideans.txt", "w");
    for (int i = 1; i <= NUMOFMATH; i++)
    {
        int beiChuShu = rand() % mod1 + 1;
        int chuShu = rand() % mod2 + 1;
        if (chuShu <= 1 || beiChuShu <= 1)
        {
            i--;
            continue;
        }
        int ans1 = beiChuShu / chuShu;
        int ans2 = beiChuShu % chuShu;
        if (!check(ans1))
        {
            i--;
            continue;
        }
        fprintf(fp, "%d : %d ÷ %d =__.....__   \n", i, beiChuShu, chuShu);
        fprintf(fp2, "%d : %d……%d\n", i, ans1, ans2);
    }
    return 0;
}