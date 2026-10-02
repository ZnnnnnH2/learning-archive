#include <iostream>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <algorithm>
#include <vector>

typedef long long ll;
typedef int *intt;
typedef char *charr;

using namespace std;
const int inf = 0x3f3f3f3f;
const int N = 1e5 + 5;

struct node
{
    int x, y;

    node() : x(0), y(0) {}
    node(int x, int y) : x(x), y(y) {}

    bool operator==(const node &a) const
    {
        return x == a.x && y == a.y;
    }
    bool operator!=(const node &a) const
    {
        return !(*this == a);
    }
};
char qz[] = {'k', 'q', 'r', 'b', 'n', 'p'};
char QZ[] = {'K', 'Q', 'R', 'B', 'N', 'P'};
const int T = 9;
struct chess
{
    int t;
    node p[6][T];
    node q[6][T];
    bool operator==(const chess &a) const
    {
        for (int i = 0; i < 6; i++)
        {
            for(int j=0;j<T;j++)
            {
                if(p[i][j]!=a.p[i][j]||q[i][j]!=a.q[i][j])
                {
                    return false;
                }
            }
        }
        return true;
    }
} ch[100];
int checkChess(char c)
{
    for (int i = 0; i < 6; i++)
    {
        if (c == qz[i])
        {
            return i;
        }
    }
    for (int i = 0; i < 6; i++)
    {
        if (c == QZ[i])
        {
            return -i;
        }
    }
    return inf;
}
int main()
{
    // freopen("1203in.txt", "r", stdin);
    // freopen("1203out.txt", "w", stdout);
    int n;
    cin >> n;
    string str;
    int tot = 0;
    for (int i = 0; i < n; i++)
    {
        chess cs;
        for (int j = 0; j < 8; j++)
        {
            cin >> str;
            for (int k = 0; k < 8; k++)
            {
                int index = checkChess(str[k]);
                if (index != inf)
                {
                    if (index > 0)
                    {
                        int &mun = cs.q[index][0].x;
                        mun++;
                        cs.q[index][mun].x = j;
                        cs.q[index][mun].y = k;
                    }
                    else
                    {
                        int &mun = cs.p[-index][0].x;
                        mun++;
                        cs.p[-index][mun].x = j;
                        cs.p[-index][mun].y = k;
                    }
                }
            }
        }
        for (int j = 0; j < tot; j++)
        {
            if (ch[j] == cs)
            {
                ch[j].t++;
                cout << ch[j].t << endl;
                goto end;
            }
        }
        ch[tot] = cs;
        cout << 1 << endl;
        ch[tot++].t = 1;
    end:;
    }
    return 0;
}