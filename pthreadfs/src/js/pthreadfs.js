/**
 * @license
 * Copyright 2021 The Emscripten Authors
 * SPDX-License-Identifier: MIT
 */

var SyscallWrappers = {}

let SyscallsFunctions = [
  {'name': 'open', 'args': ['path', 'flags', 'varargs']},
  {'name': 'unlink', 'args': ['path']},
  {'name': 'chdir', 'args': ['path']},
  {'name': 'mknod', 'args': ['path', 'mode', 'dev']},
  {'name': 'chmod', 'args': ['path', 'mode']},
  {'name': 'access', 'args': ['path', 'amode']},
  {'name': 'rename', 'args': ['old_path', 'new_path']},
  {'name': 'mkdir', 'args': ['path', 'mode']},
  {'name': 'rmdir', 'args': ['path']},
  {'name': 'ioctl', 'args': ['fd', 'request', 'varargs']},
  {'name': 'readlink', 'args': ['path', 'buf', 'bufsize']},
  {'name': 'fchmod', 'args': ['fd', 'mode']},
  {'name': 'fchdir', 'args': ['fd']},
  {'name': 'fdatasync', 'args': ['fd']},
  {'name': 'truncate64', 'args': ['path', 'zero', 'low', 'high']},
  {'name': 'ftruncate64', 'args': ['fd', 'zero', 'low', 'high']},
  {'name': 'stat64', 'args': ['path', 'buf']},
  {'name': 'lstat64', 'args': ['path', 'buf']},
  {'name': 'fstat64', 'args': ['fd', 'buf']},
  {'name': 'lchown32', 'args': ['path', 'owner', 'group']},
  {'name': 'fchown32', 'args': ['fd', 'owner', 'group']},
  {'name': 'chown32', 'args': ['path', 'owner', 'group']},
  {'name': 'getdents64', 'args': ['fd', 'dirp', 'count']},
  {'name': 'fcntl64', 'args': ['fd', 'cmd', 'varargs']},
  {'name': 'statfs64', 'args': ['path', 'size', 'buf']},
  {'name': 'fstatfs64', 'args': ['fd', 'size', 'buf']},
  {'name': 'fallocate', 'args': ['fd', 'mode', 'off_low', 'off_high', 'len_low', 'len_high']},
]

let WasiFunctions = [
  {'name': 'write', 'args': ['iovs', 'iovs_len', 'nwritten']},
  {'name': 'read', 'args': ['iovs', 'iovs_len', 'nread']},
  {'name': 'close', 'args': []},
  {'name': 'pwrite', 'args': ['iov', 'iovcnt', "{{{ defineI64Param('offset') }}}", 'pnum']},
  {'name': 'pread', 'args': ['iov', 'iovcnt', "{{{ defineI64Param('offset') }}}", 'pnum']},
  {'name': 'seek', 'args': ["{{{ defineI64Param('offset') }}}", 'whence', 'newOffset']},
  {'name': 'fdstat_get', 'args': ['pbuf']},
  {'name': 'sync', 'args': []},
]

function createWasiWrapper(name, args, wrappers) {
  let full_args = 'fd';
  if (args.length > 0) {
    full_args = full_args + ',' + args.join(',');
  }
  let full_args_with_resume = full_args + ',resume';
  let wrapper = `function(${full_args_with_resume}) {`;
  wrapper += `_fd_${name}_async(${full_args}).then((res) => {`;
  wrapper += 'wasmTable.get(resume)(res);});}'
  wrappers[`__fd_${name}_async`] = eval('(' + wrapper + ')');
  wrappers[`__fd_${name}_async__deps`] = [`fd_${name}_async`, '$ASYNCSYSCALLS', '$FSAFS', '$SFAFS'];
}

function createSyscallWrapper(name, args, wrappers) {
  let full_args = '';
  let full_args_with_resume = 'resume';
  if (args.length > 0) {
    full_args = args.join(',');
    full_args_with_resume = full_args + ', resume';
  }
  let wrapper = `function(${full_args_with_resume}) {`;
  wrapper += `_${name}_async(${full_args}).then((res) => {`;
  wrapper += 'wasmTable.get(resume)(res);});}'
  wrappers[`__sys_${name}_async`] = eval('(' + wrapper + ')');
  wrappers[`__sys_${name}_async__deps`] = [`${name}_async`, '$ASYNCSYSCALLS', '$FSAFS', '$SFAFS'];
}

for (x of WasiFunctions) {
  createWasiWrapper(x.name, x.args, SyscallWrappers);
}
for (x of SyscallsFunctions) {
  createSyscallWrapper(x.name, x.args, SyscallWrappers);
}

SyscallWrappers['init_pthreadfs'] = function (resume) {
  
  let access_handle_detection = async function() {
  const root = await navigator.storage.getDirectory();
  const present = FileSystemFileHandle.prototype.createSyncAccessHandle !== undefined;
  return present;
}

let storage_foundation_detection = function() {
  if (typeof storageFoundation == typeof undefined) {
    return false;
  }
  if (storageFoundation.requestCapacitySync(1) === 0) {
    return false;
  }
  return true;
}
  var FSNode = /** @constructor */ function(parent, name, mode, rdev) {
    if (!parent) {
      parent = this;  // root node sets parent to itself
    }
    this.parent = parent;
    this.mount = parent.mount;
    this.mounted = null;
    this.id = PThreadFS.nextInode++;
    this.name = name;
    this.mode = mode;
    this.node_ops = {};
    this.stream_ops = {};
    this.rdev = rdev;
  };
  var readMode = 292/*{{{ cDefine("S_IRUGO") }}}*/ | 73/*{{{ cDefine("S_IXUGO") }}}*/;
  var writeMode = 146/*{{{ cDefine("S_IWUGO") }}}*/;
  Object.defineProperties(FSNode.prototype, {
   read: {
    get: /** @this{FSNode} */function() {
     return (this.mode & readMode) === readMode;
    },
    set: /** @this{FSNode} */function(val) {
     val ? this.mode |= readMode : this.mode &= ~readMode;
    }
   },
   write: {
    get: /** @this{FSNode} */function() {
     return (this.mode & writeMode) === writeMode;
    },
    set: /** @this{FSNode} */function(val) {
     val ? this.mode |= writeMode : this.mode &= ~writeMode;
    }
   },
   isFolder: {
    get: /** @this{FSNode} */function() {
     return PThreadFS.isDir(this.mode);
    }
   },
   isDevice: {
    get: /** @this{FSNode} */function() {
     return PThreadFS.isChrdev(this.mode);
    }
   }
  });
  PThreadFS.FSNode = FSNode;

  PThreadFS.staticInit().then(async ()=> {
    PThreadFS.ignorePermissions = false;
    await PThreadFS.mkdir('/pthreadfs');
    let has_access_handles = await access_handle_detection();
    let has_storage_foundation = storage_foundation_detection();

    if (has_access_handles) {
      await PThreadFS.mount(FSAFS, { root: '.' }, '/pthreadfs');
      console.log('Initialized PThreadFS with OPFS Access Handles');

      if ("pthreadfs_preload" in Module) {
        await Module["pthreadfs_preload"]();
      }
      else {
        console.log('No init code provided');
      }
      wasmTable.get(resume)();
      return;
    }
    if (has_storage_foundation) {
      await PThreadFS.mount(SFAFS, { root: '.' }, '/pthreadfs');
  
      // Storage Foundation requires explicit capacity allocations.
      if (storageFoundation.requestCapacity) {
        await storageFoundation.requestCapacity(1024*1024*1024);
      }
      console.log('Initialized PThreadFS with Storage Foundation API');
      wasmTable.get(resume)();
      return;
    }
    console.log('Initialized PThreadFS with MEMFS');
    wasmTable.get(resume)();
  });
}

// Initialize a backend for PThreadFS.
// PThreadFS can only work with a single backend at a time. The initialization code
// checks which backends are available and picks from the following list:
// 1. OPFS Access Handles - see https://github.com/WICG/file-system-access/blob/main/AccessHandle.md
// 2. Storage Foundation API - https://github.com/WICG/storage-foundation-api-explainer
// 3. Emscripten's in-Memory file system (MEMFS).
SyscallWrappers['init_backend'] = function(resume) {

  let access_handle_detection = async function() {
    const root = await navigator.storage.getDirectory();
    const file = await root.getFileHandle('access-handle-detect', { create: true });
    const present = file.createSyncAccessHandle != undefined;
    await root.removeEntry('access-handle-detect');
    return present;
  }

  let storage_foundation_detection = function() {
    if (typeof storageFoundation == typeof undefined) {
      return false;
    }
    if (storageFoundation.requestCapacitySync(1) === 0) {
      return false;
    }
    return true;
  }

  PThreadFS.mkdir('/pthreadfs').then(async () => {
    let has_access_handles = await access_handle_detection();
    let has_storage_foundation = storage_foundation_detection();

    if (has_access_handles) {
      await PThreadFS.mount(FSAFS, { root: '.' }, '/pthreadfs');
      console.log('Initialized PThreadFS with OPFS Access Handles');
      wasmTable.get(resume)();
      return;
    }
    if (has_storage_foundation) {
      await PThreadFS.mount(SFAFS, { root: '.' }, '/pthreadfs');
  
      // Storage Foundation requires explicit capacity allocations.
      if (storageFoundation.requestCapacity) {
        await storageFoundation.requestCapacity(1024*1024*1024);
      }
      console.log('Initialized PThreadFS with Storage Foundation API');
      wasmTable.get(resume)();
      return;
    }
    console.log('Initialized PThreadFS with MEMFS');
    wasmTable.get(resume)();
  });
}

mergeInto(LibraryManager.library, SyscallWrappers);
