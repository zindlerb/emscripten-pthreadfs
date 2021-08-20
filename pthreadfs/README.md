# PThreadFS

The Emscripten Pthread File System (PThreadFS) unlocks using (partly) asynchronous storage APIs such as [OPFS Access Handles](https://docs.google.com/document/d/121OZpRk7bKSF7qU3kQLqAEUVSNxqREnE98malHYwWec/edit#heading=h.gj2fudnvy982) through the Emscripten File System API. This enables C++ applications compiled through Emscripten to use persistent storage without using [Asyncify](https://emscripten.org/docs/porting/asyncify.html). PThreadFS requires only minimal modifications to the C++ code and nearly achieves feature parity with the Emscripten's classic File System API.

PThreadFS works by replacing Emscripten's file system API with a new API that proxies all file system operations to a dedicated pthread. This dedicated thread maintains a virtual file system that can use different APIs as backend (very similar to the way Emscripten's VFS is designed). In particular, PThreadFS comes with built-in support for asynchronous backends such as [OPFS Access Handles](https://docs.google.com/document/d/121OZpRk7bKSF7qU3kQLqAEUVSNxqREnE98malHYwWec/edit#heading=h.gj2fudnvy982).
Although the underlying storage API is asynchronous, PThreadFS makes it appear synchronous to the C++ application.

The code is still prototype quality and **should not be used in a production environment** for the time being.

## Enable and detect OPFS in Chrome

OPFS Access Handles require very recent versions of Google Chrome Canary. PThreadFS has been successfully tested with Version 94.0.4597.0.

To enable the API, the " --enable-features=FileSystemAccessAccessHandle" flag must be set when starting Chrome from the console. On MacOS, this can be done through
```
open -a /Applications/Google\ Chrome\ Canary.app --args --enable-features=FileSystemAccessAccessHandle
```

Support for AccesHandles in OPFS can be detected through
```
async function detectAccessHandleWorker() {
  const root = await navigator.storage.getDirectory();
  const file = await root.getFileHandle('access-handle-detect', { create: true });
  const present = file.createSyncAccessHandle != undefined;
  await root.removeEntry('access-handle-detect');
  return present;
}

async function detectAccessHandleMainThread() {
  const detectAccessHandleAndPostMessage = async function(){
    const root = await navigator.storage.getDirectory();
    const file = await root.getFileHandle('access-handle-detect', { create: true });
    const present = file.createSyncAccessHandle != undefined;
    await root.removeEntry('access-handle-detect');
    postMessage(present);
  };

  return new Promise((resolve, reject) => {
    const detectBlob = new Blob(['('+detectAccessHandleAndPostMessage.toString()+')()'], {type: 'text/javascript'})
    const detectWorker = new Worker(window.URL.createObjectURL(detectBlob));
    
    detectWorker.onmessage = result => {
      resolve(result.data);
      detectWorker.terminate();
    };

    detectWorker.onerror = error => {
      reject(error);
      detectWorker.terminate();
    };
  });
}
```

## Getting the code

PthreadFS is available on Github in the [emscripten-pthreadfs](https://github.com/rstz/emscripten-pthreadfs) repository. All code resides in the `pthreadfs` folder. It should be usable with any up-to-date Emscripten version. 

There is **no need** to use a fork of Emscripten itself since all code operates in user-space.

## Using PThreadFS in a project

In order to use the code in a new project, you only need the three files in the `pthreadfs` folder: `pthreadfs_library.js`, `pthreadfs.cpp` and `pthreadfs.h`. The files are included as follows:

### Code changes

- Include `pthreadfs.h` in the C++ file containing `main()`:
```
#include "pthreadfs.h"
```
- Call `emscripten_init_pthreadfs();` at the top of `main()` (or before any file system syscalls).
- PThreadFS maintains a virtual file system. The OPFS backend is mounted at `/filesystemaccess/`. Only files in this folder are persisted between sessions. All other files will be stored in-memory through MEMFS.

### Build process changes

There are two changes required to build a project with PThreadFS:
- Compile `pthreadfs.h` and `pthreadfs.cpp` and link the resulting object to your application. Add `-pthread` to the compiler flag to include support for pthreads.
- Add the following options to the linking step:
```
-pthread -O3 -s PROXY_TO_PTHREAD --js-library=library_pthreadsfs.js
```
**Example**
If your build process was 
```shell
emcc myproject.cpp -o myproject.html
```
Your new build step should be
```shell
emcc -pthread -s PROXY_TO_PTHREAD -O3 --js-library=library_pthreadfs.js myproject.cpp pthreadfs.cpp -o myproject.html
```

### Advanced Usage

If you want to modify the PThreadFS file system directly, you may use the macro `EM_PTHREADFS_ASM()` defined in `pthreadfs.h`. The macro allows you to run asynchrononous Javascript on the Pthread hosting the PThreadFS file system. For example, you may create a folder in the virtual file system by calling
```
EM_PTHREADFS_ASM(
  await PThreadFS.mkdir('mydirectory');
);
```
See `pthreadfs/examples/emscripten-tests/fsafs.cpp` for exemplary usage.


## Known Limitations

- All files to be stored using the file system access Access Handles must be stored in the `/filesystemaccess` folder.
- Files in the `/filesystemaccess` folder cannot interact through syscalls with other files (e.g. moving, copying, etc.).
- The code is still prototype quality and **should not be used in a production environment** yet. It is possible that the use of PThreadFS might lead to subtle bugs in other libraries.
- PThreadFS requires PROXY_TO_PTHREAD to be active. In particular, no system calls interacting with the file system should be called from the main thread.
- Some functionality of the Emscripten File System API is missing, such as sockets, IndexedDB integration and support for XHRequests.
- PThreadFS depends on C++ libraries. `EM_PTRHEADFS_ASM()` cannot be used within C files (although initializing through `emscripten_init_pthreadfs()` is possible, see the `pthreadfs/examples/sqlite-speedtest` for an example).
- Performance is good if and only if full optimizations (compiler option `-O3`) are enabled and DevTools are closed.

## Examples

The examples are provided to show how projects can be transformed to use PThreadFS. To build them, navigate to the `pthreadfs/examples/` folder and run `make all`. You need to have the [Emscripten SDK](https://emscripten.org/docs/getting_started/downloads.html) activated for the build process to succeed.

### SQLite Speedtest

This example shows how to compile and run the [speedtest1](https://www.sqlite.org/cpu.html) from the SQLite project in the browser.

The Makefile downloads the source of the speedtest and sqlite3 directly from <https://sqlite.org>.

To compile, navigate to the `pthreadfs/examples/` directory and run

```shell
make sqlite-speedtest
cd dist/sqlite-speedtest
python3 -m http.server 8888
```
Then open the following link in a Chrome instance with the
_OPFS Access Handles_ [enabled](#enable-and-detect-opfs-in-chrome):

[localhost:8888/sqlite-speedtest](http://localhost:8888/sqlite-speedtest). The results of the speedtest can be found in the DevTools console.

### Other tests

The folder `pthreadfs/examples/emscripten-tests` contains a number of other file system tests taken from Emscripten's standard test suite.

To compile, navigate to the `pthreadfs/examples/` directory and run

```shell
make emscripten-tests
cd dist/emscripten-tests
python3 -m http.server 8888
```
Then open the following link in a Chrome instance with the
_OPFS Access Handles_ [enabled](#enable-and-detect-opfs-in-chrome):

[localhost:8888/emscripten-tests](http://localhost:8888/emscripten-tests) and choose a test. The results of the test can be found in the DevTools console.

## Authors
- Richard Stotz (<rstz@chromium.org>)

This is not an official Google product.