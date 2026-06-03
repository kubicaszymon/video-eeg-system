
#include "Logger.h"

void test_1()
{
    Logger log(1, "test_1");
    for(int i = 0; i < 10; i++)
        log.next_sample();
}

void test_2()
{
    Logger log(2, "test_2");
    for(int i = 0; i < 20; i++)
        log.next_sample();
}

void test_3()
{
    const int N = 10 * 1000 * 1000;
    Logger log(N / 10, "test_3");
    for(int i = 0; i < N; i++)
        log.next_sample();
}

int main()
{
    Logger::print_to_stderr = true;
    test_1();
    test_2();
    test_3();
    return 0;
}

