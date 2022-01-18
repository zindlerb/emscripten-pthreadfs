/**
 * @license
 * Copyright 2021 The Emscripten Authors
 * SPDX-License-Identifier: MIT
 */

mergeInto(LibraryManager.library, {
  $FSAFS__deps: ['$PThreadFS'],
  $FSAFS: {

    /* Debugging */

    debug: function(...args) {
      // Uncomment to print debug information.
      //
      // console.log(args);
    },

    /* Helper functions */

    // This function mantains backwards compatibility with Chrome versions
    // before M98. It should be removed once there is no risk of encountering
    // an old versions that does not take a parameter on createSyncAccessHandle.
    createSyncAccessHandle: async function(node) {
      if(FileSystemFileHandle.prototype.createSyncAccessHandle.length == 0) {
        return await node.localReference.createSyncAccessHandle();
      }
      return await node.localReference.createSyncAccessHandle({mode: "in-place"});
    },

    /* Filesystem implementation (public interface) */

    createNode: function (parent, name, mode, dev) {
      FSAFS.debug('createNode', arguments);
      if (!PThreadFS.isDir(mode) && !PThreadFS.isFile(mode)) {
        throw new PThreadFS.ErrnoError({{{ cDefine('EINVAL') }}});
      }
      var node = PThreadFS.createNode(parent, name, mode);
      node.node_ops = FSAFS.node_ops;
      node.stream_ops = FSAFS.stream_ops;
      if (PThreadFS.isDir(mode)) {
        node.contents = {};
      }
      node.timestamp = Date.now();
      // add the new node to the parent
      if (parent) {
        parent.contents[name] = node;
        parent.timestamp = node.timestamp;
      }
      return node;
    },

    mount: async function (mount) {
      FSAFS.debug('mount', arguments);
      let node = FSAFS.createNode(null, '/', {{{ cDefine('S_IFDIR') }}} | 511 /* 0777 */, 0);
      FSAFS.root = await navigator.storage.getDirectory();
      node.localReference = FSAFS.root;
      return node;
    },

    /* Operations on the nodes of the filesystem tree */

    node_ops: {
      getattr: async function(node) {
        FSAFS.debug('getattr', arguments);
        var attr = {};
        // device numbers reuse inode numbers.
        attr.dev = PThreadFS.isChrdev(node.mode) ? node.id : 1;
        attr.ino = node.id;
        attr.mode = node.mode;
        attr.nlink = 1;
        attr.uid = 0;
        attr.gid = 0;
        attr.rdev = node.rdev;
        if (PThreadFS.isDir(node.mode)) {
          attr.size = 4096;
        } else if (PThreadFS.isFile(node.mode)) {
          if (ENVIRONMENT_IS_WEB){
            // Since Access Handles are unavailable in workers, we must use
            // file blobs instead.
            let file_blob = await node.localReference.getFile();
            attr.size = file_blob.size;
          }
          else {  // !ENVIRONMENT_IS_WEB
            if (node.handle) {
              attr.size = await node.handle.getSize();
            }
            else {
              let fileHandle = await FSAFS.createSyncAccessHandle(node);
              attr.size = await fileHandle.getSize();
              await fileHandle.close();
            }
          }
        } else if (PThreadFS.isLink(node.mode)) {
          attr.size = node.link.length;
        } else {
          attr.size = 0;
        }
        attr.atime = new Date(node.timestamp);
        attr.mtime = new Date(node.timestamp);
        attr.ctime = new Date(node.timestamp);
        // NOTE: In our implementation, st_blocks = Math.ceil(st_size/st_blksize),
        //       but this is not required by the standard.
        attr.blksize = 4096;
        attr.blocks = Math.ceil(attr.size / attr.blksize);
        return attr;
      },

      setattr: async function(node, attr) {
        FSAFS.debug('setattr', arguments);
        if (attr.mode !== undefined) {
          node.mode = attr.mode;
        }
        if (attr.timestamp !== undefined) {
          node.timestamp = attr.timestamp;
        }
        if (attr.size !== undefined) {
          if (ENVIRONMENT_IS_WEB) {
            // Since Access Handles are unavailable in workers, we must use 
            // writables instead.
            let wt = await node.localReference.createWritable({ keepExistingData: true});
            await wt.truncate(attr.size);
            await wt.close();
            return;
          }
          if (node.handle) {
            await node.handle.truncate(attr.size);
            return;
          }
          // On a worker without an open access handle, try three times to open an access handle.
          function timeout(ms) { return new Promise(resolve => setTimeout(resolve, ms)) };
          const number_of_tries = 3;
          const waiting_time_ms = 100;
          let handle;
          for (let trial = 0; trial < number_of_tries; trial++) {
            try {
              handle = await FSAFS.createSyncAccessHandle(node);
              await handle.truncate(attr.size);
              await handle.close();
              return;
            }
            catch (e) {
              if (typeof handle !== "undefined") {
                try {
                  await handle.close();
                }
                catch (e) {
                  console.log('FSAFS error (setattr): Closing handle failed.');
                }
              }
              // Access Handles throw InvalidStateErrors if the file is locked.
              if (e.name === "InvalidStateError") {
                console.log(`FSAFS warning: Truncating an access handle failed. Is the file open? Trying again.`);
              }
              else {
                console.log(`FSAFS warning: Truncating an access handle failed with unexpected error ${e.name}. Trying again.`);
              }
            }
            await timeout(waiting_time_ms);
          }
          console.log(`FSAFS warning: Truncating access handle failed after multiple attempts, aborting`);
          throw PThreadFS.genericErrors[{{{ cDefine('EBUSY') }}}];
        }
      },

      lookup: async function (parent, name) {
        FSAFS.debug('lookup', arguments);
        let childLocalReference = null;
        let mode = null;
        try {
          childLocalReference = await parent.localReference.getDirectoryHandle(name, {create: false});
          mode = {{{ cDefine('S_IFDIR') }}} | 511 /* 0777 */
        } catch (e) {
          try {
            childLocalReference = await parent.localReference.getFileHandle(name, {create: false});
            mode = {{{ cDefine('S_IFREG') }}} | 511 /* 0777 */
          } catch (e) {
            throw PThreadFS.genericErrors[{{{ cDefine('ENOENT') }}}];
          }
        }
        var node = PThreadFS.createNode(parent, name, mode);
        node.node_ops = FSAFS.node_ops;
        node.stream_ops = FSAFS.stream_ops;
        node.localReference = childLocalReference;
        if (childLocalReference.kind === 'directory') {
          node.contents = {};
        }
        return node;
      },

      mknod: async function (parent, name, mode, dev) {
        FSAFS.debug('mknod', arguments);
        let node = FSAFS.createNode(parent, name, mode, dev);
        try {
          if (PThreadFS.isDir(mode)) {
            node.localReference = await parent.localReference.getDirectoryHandle(name, {create: true});
          } else if (PThreadFS.isFile(mode)) {
            node.localReference = await parent.localReference.getFileHandle(name, {create: true});
          }
        } catch (e) {
          if (!('code' in e)) throw e;
          throw new PThreadFS.ErrnoError(-e.errno);
        }

        node.handle = null;
        node.refcount = 0;
        return node;
      },

      rename: async function (oldNode, newParentNode, newName) {
        FSAFS.debug('rename', arguments);
        if (PThreadFS.isDir(oldNode.mode)) {
          console.log('Rename error: File System Access does not support renaming directories');
          throw new PThreadFS.ErrnoError({{{ cDefine('EXDEV') }}});
        }
        try {
          await oldNode.localReference.move(newParentNode.localReference, newName);
        }
        catch (e) {
          console.log('FSAFS error: Rename failed');
          if (!('localReference' in oldNode )|| !('localReference' in newParentNode)) {
            console.log('No local reference to one of the nodes stored.');
          }
          else if (!('move' in oldNode.localReference)) {
            console.log('File System Access move() not available. Try enabling Experimental Web Platform features in chrome://flags');
          }
          else if (e.name == "InvalidStateError") {
            console.log('Rename error: Did you try to rename an open file?');
          }
          else {
            console.log('Unknown rename error ' + e);
          }
          throw new PThreadFS.ErrnoError({{{ cDefine('EXDEV') }}});
        }
        // Update the internal directory cache.
        delete oldNode.parent.contents[oldNode.name];
        oldNode.parent.timestamp = Date.now()
        oldNode.name = newName;
        newParentNode.contents[newName] = oldNode;
        newParentNode.timestamp = oldNode.parent.timestamp;
        oldNode.parent = newParentNode;
      },

      unlink: async function(parent, name) {
        FSAFS.debug('unlink', arguments);
        let res = await parent.localReference.removeEntry(name);

        if ('contents' in parent) {
          delete parent.contents[name];
        }
        parent.timestamp = Date.now();
        return res;
      },

      rmdir: async function(parent, name) {
        FSAFS.debug('rmdir', arguments);
        let res;
        try{
          res = await parent.localReference.removeEntry(name);
        } catch(e) {
          // Do not use `for await`, since Emscripten's minifier does not support it.
          let it = parent.localReference.values();
          let res = await it.next();
          if (!res.done) {
            throw new FS.ErrnoError({{{ cDefine('ENOTEMPTY') }}});
          }
          throw new FS.ErrnoError({{{ cDefine('EINVAL') }}});
        }
        if ('contents' in parent) {
          delete parent.contents[name];
        }
        parent.timestamp = Date.now();
        return res
      },

      readdir: async function(node) {
        FSAFS.debug('readdir', arguments);
        let entries = ['.', '..'];
        // Do not use `for await` yet, since it's not supported by Emscripten's minifier.
        // for await (let [name, handle] of node.localReference) {
        //   entries.push(name);
        // }
        let it = node.localReference.values();
        let curr = await it.next();
        while (!curr.done) {
          entries.push(curr.value.name);
          curr = await it.next();
        }
        return entries;
      },

      symlink: function(parent, newName, oldPath) {
        console.log('FSAFS error: symlink is not implemented')
        throw new PThreadFS.ErrnoError({{{ cDefine('EXDEV') }}});
      },

      readlink: function(node) {
        console.log('FSAFS error: readlink is not implemented')
        throw new PThreadFS.ErrnoError({{{ cDefine('ENOSYS') }}});
      },
    },

    /* Operations on file streams (i.e., file handles) */

    stream_ops: {
      open: async function (stream) {
        FSAFS.debug('open', arguments);
        if (PThreadFS.isDir(stream.node.mode)) {
          // Everything is correctly set up already
          return;
        }
        if (!PThreadFS.isFile(stream.node.mode)) {
          console.log('FSAFS error: open is only implemented for files and directories')
          throw new PThreadFS.ErrnoError({{{ cDefine('ENOSYS') }}});
        }

        if (stream.node.handle) {
          stream.handle = stream.node.handle;
          ++stream.node.refcount;
        } else {
          if (ENVIRONMENT_IS_WEB) {
            stream.handle = stream.node.localReference;
          }
          else {
            stream.handle = await FSAFS.createSyncAccessHandle(stream.node);
          }
          stream.node.handle = stream.handle;
          stream.node.refcount = 1;
        }
      },

      close: async function (stream) {
        FSAFS.debug('close', arguments);
        if (PThreadFS.isDir(stream.node.mode)) {
          // Everything is correctly set up already
          return;
        }
        if (!PThreadFS.isFile(stream.node.mode)) {
          console.log('FSAFS error: close is only implemented for files and directories');
          throw new PThreadFS.ErrnoError({{{ cDefine('ENOSYS') }}});
        }

        stream.handle = null;
        --stream.node.refcount;
        if (stream.node.refcount <= 0) {
          // On the main thread, no access handle is open.
          if (!ENVIRONMENT_IS_WEB) {
            await stream.node.handle.close();
          }
          stream.node.handle = null;
        }
      },

      fsync: async function(stream) {
        FSAFS.debug('fsync', arguments);
        if (stream.handle == null) {
          throw new PThreadFS.ErrnoError({{{ cDefine('EBADF') }}});
        }
        if (!ENVIRONMENT_IS_WEB) {
          // On worker threads, explicit flush is required. On the main thread,
          // writables are used that flush implicitly.
          await stream.handle.flush();
        }
        return 0;
      },

      read: async function (stream, buffer, offset, length, position) {
        FSAFS.debug('read', arguments);
        let data = buffer.subarray(offset, offset+length);
        let readBytes;
        if (ENVIRONMENT_IS_WEB) {
          // On the main thread, we use file blobs instead of Access Handles.
          let file_blob = await stream.handle.getFile();
          let file_arraybuffer = await file_blob.arrayBuffer();
          var file_uint8view = new Uint8Array(file_arraybuffer);
          let read_maximum = Math.min(position + data.length, file_blob.size);
          data.set(file_uint8view.slice(position, read_maximum));
          readBytes = read_maximum - position;
        }
        else {
          readBytes = await stream.handle.read(data, {at: position});
        }
        return readBytes;
      },

      write: async function (stream, buffer, offset, length, position) {
        FSAFS.debug('write', arguments);
        stream.node.timestamp = Date.now();
        let data = buffer.subarray(offset, offset+length);
        let writtenBytes;
        if (ENVIRONMENT_IS_WEB) {
          // On the main thread, we use writables instead of Access Handles.
          // This may be really slow, since it always copies the entire file.
          let writable = await stream.handle.createWritable({ keepExistingData: true});
          await writable.write({type: "write", position: position, data: data});
          await writable.close();
          writtenBytes = data.length;
        }
        else {
          writtenBytes = await stream.handle.write(data, {at: position});
        }
        return writtenBytes;
      },

      llseek: async function (stream, offset, whence) {
        FSAFS.debug('llseek', arguments);
        let position = offset;
        if (whence === {{{ cDefine('SEEK_CUR') }}}) {
          position += stream.position;
        } else if (whence === {{{ cDefine('SEEK_END') }}}) {
          if (PThreadFS.isFile(stream.node.mode)) {
            if (ENVIRONMENT_IS_WEB) {
              // On the main thread, file blobs are used to determine a file's
              // size.
              let file_blob = await stream.handle.getFile();
              position += file_blob.size;
            }
            else {
              position += await stream.handle.getSize();
            }
          }
        } 

        if (position < 0) {
          throw new PThreadFS.ErrnoError({{{ cDefine('EINVAL') }}});
        }
        return position;
      },

      mmap: function(stream, buffer, offset, length, position, prot, flags) {
        FSAFS.debug('mmap', arguments);
        throw new PThreadFS.ErrnoError({{{ cDefine('EOPNOTSUPP') }}});
      },

      msync: function(stream, buffer, offset, length, mmapFlags) {
        FSAFS.debug('msync', arguments);
        throw new PThreadFS.ErrnoError({{{ cDefine('EOPNOTSUPP') }}});
      },

      munmap: function(stream) {
        FSAFS.debug('munmap', arguments);
        throw new PThreadFS.ErrnoError({{{ cDefine('EOPNOTSUPP') }}});
      },
    }
  }
});
