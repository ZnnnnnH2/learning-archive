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
const int N = 1e4 + 5;
const int D = 25;
ll q[N][D], k[N][D], kt[D][N], v[N][D], w[N];
ll ans1[D][D];

int main()
{
    int n, d;
    scanf("%d%d", &n, &d);
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            scanf("%lld", &q[i][j]);
        }
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            scanf("%lld", &k[i][j]);
        }
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            scanf("%lld", &v[i][j]);
        }
    }
    for (int i = 1; i <= n; i++)
    {
        scanf("%lld", &w[i]);
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            kt[j][i] = k[i][j];
        }
    }
    for (int i = 1; i <= d; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            ans1[i][j] = 0;
            for (int t = 1; t <= n; t++)
            {
                ans1[i][j] += kt[i][t] * v[t][j];
            }
        }
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            k[i][j] = 0;
            for (int t = 1; t <= d; t++)
            {
                k[i][j] += q[i][t] * ans1[t][j];
            }
        }
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            k[i][j] *= w[i];
        }
    }
    for (int i = 1; i <= n; i++)
    {
        for (int j = 1; j <= d; j++)
        {
            printf("%lld ", k[i][j]);
        }
        printf("\n");
    }
    return 0;
}