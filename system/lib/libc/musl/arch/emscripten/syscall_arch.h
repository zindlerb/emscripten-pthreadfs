#define __SYSCALL_LL_E(x) \
((union { long long ll; long l[2]; }){ .ll = x }).l[0], \
((union { long long ll; long l[2]; }){ .ll = x }).l[1]
#define __SYSCALL_LL_O(x) 0, __SYSCALL_LL_E((x))

#define __SC_socket      1
#define __SC_bind        2
#define __SC_connect     3
#define __SC_listen      4
#define __SC_accept      5
#define __SC_getsockname 6
#define __SC_getpeername 7
#define __SC_socketpair  8
#define __SC_send        9
#define __SC_recv        10
#define __SC_sendto      11
#define __SC_recvfrom    12
#define __SC_shutdown    13
#define __SC_setsockopt  14
#define __SC_getsockopt  15
#define __SC_sendmsg     16
#define __SC_recvmsg     17
#define __SC_accept4     18
#define __SC_recvmmsg    19
#define __SC_sendmmsg    20

// static syscalls. we must have one non-variadic argument before the rest due to ISO C.

#ifdef __cplusplus
extern "C" {
#endif

long __syscall1(int status);
long __syscall3(int stream, int buf, int count);
long __syscall4(int stream, int buf, int count);
long __syscall5(int pathname, int flags, int mode);
long __syscall6(int stream);
long __syscall9(int oldpath, int newpath);
long __syscall10(int path);
long __syscall12(int path);
long __syscall14(int path, int mode, int dev);
long __syscall15(int path, int mode);
long __syscall20(void);
long __syscall29(void);
long __syscall33(int filename, int amode);
long __syscall34(int inc);
long __syscall36(void);
long __syscall38(void);
long __syscall39(int path, int mode);
long __syscall40(int path);
long __syscall41(int fd);
long __syscall42(int fdptr);
long __syscall51(int filename);
long __syscall54(int stream, int op, int _unused);
long __syscall57(int pid, int pgid);
long __syscall60(int mask);
long __syscall63(int old, int suggestFD);
long __syscall64(void);
long __syscall65(void);
long __syscall66(void);
long __syscall75(int resource, int k_rlim);
long __syscall77(int who, int usage);
long __syscall83(int target, int linkpath);
long __syscall85(int path, int buf, int bufsize);
long __syscall91(int addr, int len);
long __syscall94(int fd, int mode);
long __syscall96(int which, int who);
long __syscall97(int which, int who, int prio);
long __syscall102(void);
long __syscall104(void);
long __syscall114(void);
long __syscall118(int fd);
long __syscall121(int name, int len);
long __syscall122(int buf);
long __syscall125(int start, int len, int prot);
long __syscall132(int pid);
long __syscall133(int stream);
long __syscall140(int stream, int offset_h, int offset_l, int result, int whence);
long __syscall142(int nfds, int readfds, int writefds, int exceptfds, int timeout);
long __syscall144(int addr, int len, int flags);
long __syscall145(int stream, int iov, int iovcnt);
long __syscall146(int stream, int iov, int iovcnt);
long __syscall147(int pid);
long __syscall148(int stream);
long __syscall150(int addr, int len);
long __syscall151(int addr, int len);
long __syscall152(int flags);
long __syscall153(void);
long __syscall163(int old_addr, int old_len, int new_len, int flags, int new_addr);
long __syscall168(int fds, int nfds, int timeout);
long __syscall178(void);
long __syscall180(int stream, int buf, int count, int zero, int offset_l, int offset_h);
long __syscall181(int stream, int buf, int count, int zero, int offset_l, int offset_h);
long __syscall183(int buf, int size);
long __syscall191(int resource, int rlim);
long __syscall192(int addr, int len, int prot, int flags, int fd, int off);
long __syscall193(int path, int zero, int length_l, int length_h);
long __syscall194(int fd, int zero, int length_l, int length_h);
long __syscall195(int path, int buf);
long __syscall196(int path, int buf);
long __syscall197(int stream, int buf);
long __syscall198(int path, int owner, int group);
long __syscall199(void);
long __syscall200(void);
long __syscall201(void);
long __syscall202(void);
long __syscall203(void);
long __syscall204(void);
long __syscall205(int size, int list);
long __syscall207(int fd, int owner, int group);
long __syscall208(void);
long __syscall209(int rgid, int egid, int sgid);
long __syscall211(int rgid, int egid, int sgid);
long __syscall212(int path, int owner, int group);
long __syscall218(int addr, int len, int vec);
long __syscall219(int addr, int len, int advice);
long __syscall220(int stream, int dirp, int count);
long __syscall221(int stream, int cmd, int _unused);
long __syscall252(void);
long __syscall265(void);
long __syscall268(int path, int size, int buf);
long __syscall269(int stream, int size, int buf);
long __syscall272(int _unused, ...);
long __syscall295(int dirfd, int path, int flags, int mode);
long __syscall296(int dirfd, int path, int mode);
long __syscall297(int dirfd, int path, int mode, int dev);
long __syscall298(int dirfd, int path, int owner, int group, int flags);
long __syscall299(void);
long __syscall300(int dirfd, int path, int buf, int flags);
long __syscall301(int dirfd, int path, int flag);
long __syscall302(int olddirfd, int oldpath, int newdirfd, int newpath);
long __syscall303(int unused, ...);
long __syscall304(int target, int newdirfd, int linkpath);
long __syscall305(int fd, int path, int buf, int bufsize);
long __syscall306(int dirfd, int path, int mode, int flags);
long __syscall307(int dirfd, int path, int amode, int flags);
long __syscall308(int _unused, ...);
long __syscall320(int dirfd, int path, int times, int flag);
long __syscall324(int stream, int mode, int offset, int offset_h, int len, int len_h);
long __syscall330(int old, int suggestFD, int flags);
long __syscall331(int fd, int flag);
long __syscall333(int stream, int iov, int iovcnt, int offset, int _unused);
long __syscall334(int stream, int iov, int iovcnt, int offset, int _unused);
long __syscall337(void);
long __syscall340(int pid, int resource, int new_limit, int old_limit);
long __syscall345(void);

#undef SYS_futimesat

#ifdef __cplusplus
}
#endif
