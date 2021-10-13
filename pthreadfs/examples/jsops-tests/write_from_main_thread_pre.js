if ("preRun" in Module) {
  Module["preRun"].push( () => {
    addRunDependency('writeFiles');
    PThreadFS.init('persistent').then(async () => {
      await PThreadFS.writeFile("persistent/file.txt", "the contents of persistent/file.txt !!", {});
      await PThreadFS.createPath("/", "persistent/mainthreadfolder/subfolder/", true, true);
      await PThreadFS.writeFile("persistent/mainthreadfolder/subfolder/ok now",
        "the contents of persistent/mainthreadfolder/subfolder/ok now !!", {});
      removeRunDependency('writeFiles');
    });
  });
}
