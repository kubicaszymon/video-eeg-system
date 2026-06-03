// system independent delay
// © Copyright 2015 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#ifndef _DELAY_H
#define _DELAY_H

#if defined(__linux__) || defined(__APPLE__)
#include <unistd.h>
static void delay(unsigned msec)
{
   usleep(msec * 1000);
}
#else
#define WIN32_LEAN_AND_MEAN // Exclude rarely-used stuff from Windows headers
#include <windows.h>
static void delay(unsigned msec)
{
   Sleep(msec);
}
#endif

#endif // _DELAY_H
