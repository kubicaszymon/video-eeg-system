// BrainAmpLogger.h - BrainAmpLogger class
// © Copyright 2017 Pawel Jewstafjew Pawel<dot>Jewstafjew<at>gmail<dot>com

#ifndef _BRAINAMP_LOGGER_H
#define _BRAINAMP_LOGGER_H

#include <stdarg.h>
#include <stdio.h>
#include <assert.h>

#include <sys/timeb.h>

class Logger {
protected:
	bool stdout_enable;
	FILE * file;   

public:
   Logger(const char * name) : stdout_enable(true) {
      file = fopen(name, "a");
   }

   virtual ~Logger() {
      if (file)
	 fclose(file);
   }

  void enable_stdout(bool enable)
    { stdout_enable = enable; }

   // flush output
  virtual void flush() {
      if (file)
	 fflush(file);
      if (stdout_enable)
	 fflush(stdout);
   }

   // C-like output
   //__attribute__ (( format(printf, 2, 3) ))
   virtual int printf(const char *format, ...)
   {
      int res = 0;
      if (file) {
         va_list ap;
         va_start(ap, format);
	 res = ::vfprintf(file, format, ap);
         va_end(ap);
      }
      if (stdout_enable) {
         va_list ap;
         va_start(ap, format);
	 ::vprintf(format, ap);
         va_end(ap);
      }
      return res;
   }

   // print time stamp + EOL + flush
   virtual void timestamp() {
#ifdef _WIN32
      struct __timeb64 now;
      _ftime64(&now);
#else
      struct timeb now;
      ftime(&now);
#endif
#ifdef _WIN32
      char * timeline = _ctime64(&(now.time));
#else
      char timeline[30];
      ctime_r(&(now.time), timeline);
#endif
      timeline[19] = 0;
      this->printf("%s.%03u %s", timeline, now.millitm, &timeline[20]); // a new-line is added by ctime()
      this->flush();
   }
};

#endif // _LOGGER_H
