var Module = Module || {};
Module['arguments'] = Module['arguments'] || [];
Module['arguments'].push('3');
Module['arguments'].push(`/persistent/db${Math.random()}`);

Module['preRun'] = Module['preRun'] || [];
Module['preRun'].push(() => {
  addRunDependency('remove_files');
  navigator.storage.getDirectory().then(async (root) => {
    for await (const entry of root.values()) {
      await root.removeEntry(entry.name);
    }
    removeRunDependency('remove_files');
  });
});