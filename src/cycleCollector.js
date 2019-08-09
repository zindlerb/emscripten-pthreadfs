
function assert(x, text) {
  if (!x) throw 'Assertion failed!' + (text ? ' ' + text : '');
}

//
// A WeakSet that also allows iteration.
//
class IterableWeakSet {
  constructor(iterable) {
    // Storage for the core items.
    this.weakSet = new WeakSet();
    // An iterable list of weak refs to the items.
    this.iterable = new Set();
    // Track item => it's own weak ref, for deletion.
    this.itemToWeakRef = new WeakMap();
    // When an item dies, remove it from all tracking.
    this.finalizationGroup = new FinalizationGroup(weakRefs => {
      for (const weakRef of weakRefs) {
        this.iterable.delete(weakRef);
      }
    });
    // Add initial items, if any.
    if (iterable) {
      for (const x of iterable) {
        this.add(x);
      }
    }
  }
  add(x) {
    this.weakSet.add(x);
    const weakRef = new WeakRef(x);
    this.iterable.add(weakRef);
    this.itemToWeakRef[x] = weakRef;
    this.finalizationGroup.register(x, weakRef, weakRef);
  }
  has(x) {
    return this.weakSet.has(x):
  }
  delete(x) {
    this.weakSet.delete(x);
    const weakRef = this.itemToWeakRef[x];
    assert(weakRef);
    this.iterable.delete(weakRef);
  }
}

//
// Wraps around an arbitrary "set-like" object, translating inc/dec calls
// into an add on the set for the first inc, and a delete for the final
// dec to 0.
//
class RefCountedSet {
  constructor(setType) {
    this.set = new setType();
    this.counts = new WeakMap();
  }
  // Increments the refcount for an item. Returns true if we added it now.
  inc(x) {
    if (this.counts.has(x)) {
      this.counts[x]++;
      return false;
    } else {
      this.set.add(x);
      this.counts[x] = 1;
      return true;
    }
  }
  // Decrements the refcount for an item. Returns true if we removed it now.
  dec(x) {
    assert(this.counts.has(x));
    assert(this.counts[x] > 0);
    this.counts[x]--;
    if (this.counts[x] == 0) {
      this.set.delete(x);
      this.counts.delete(x);
      return true;
    }
    return false;
  }
  has(x) {
    return this.counts.has(x);
  }
}

//
// Manages a Table of references, handling reuse of indexes. Each tracked
// object in the table has a refcount, and is kept alive while the refcount
// remains positive.
//
class TableManager {
  constructor(table, tableStartIndex) {
    this.table = table;
    // The "top" of the table is how much of it is currently in use (either
    // actively, or in the free list of reusable indexes).
    this.tableTop = tableStartIndex;
    this.freeList = [];
    // The tracked objects and their refcounts.
    this.tracked = new RefCountedSet(WeakSet);
    // The table indexes.
    this.indexes = new WeakMap();
  }
  // Increments the refcount for an item. Returns the index in the table.
  inc(x) {
    const allocIndex = () => {
      if (this.freeList.length > 0) {
        return this.freeList.pop();
      }
      const index = this.tableTop++;
      if (this.table.length <= index) {
        this.table.grow(index - this.table.length + 1);
      }
      return index;
    };
    if (this.tracked.inc(x)) {
      this.indexes[x] = allocIndex();
    }
    return this.indexes[x];
  }
  // Decrements the refcount for an item.
  dec(x) {
    if (this.tracked.dec(x)) {
      this.freeList.push(this.indexes[x]);
      this.indexes.delete(x);
    }
  }
}

//
// CycleCollector: Manages cycle collection between a compiled VM in
// WebAssembly and the outside JavaScript VM.
//
// Notation: The "outside" is the JS VM, and the "inside" is the compiled
// VM inside it. Thus, an "external object" is the same as a JS object, which
// is referred to by a JavaScript reference, and an "internal object" is the
// same as an object in the compiled wasm VM (which lives somewhere in linear
// memory, and so is referred to by an integer pointer).
//
// This approach is designed for the case where there are few cross-VM links,
// that is most GC in the compiled VM is completely internal (which the
// compiled VM is probably well-tuned for). This collector can help remove
// cycles between the two VMs at the cost of overhead for links between
// them. If cycles are rare, it can remove them eventually, and avoid a long-
// running program leaking memory.
//
class CycleCollector {
  // When constructing a CycleCollector a wasm Table must be passed in, and
  // the start index from which we can manage it.
  constructor(table, tableStartIndex) {
    this.tableManager = new TableManager(table, tableStartIndex);
    // We must track all cross-VM links. This internal bookkeeping is weak.
    this.outgoingLinks = new Set();
    this.incomingLinks = new WeakMap();
  }
  // Add a link between an internal object to an external one. Returns the
  // table index.
  addOutgoingLink(ptr, ref) {
    var links = this.outgoingLinks[ptr];
    if (!links) {
      links = this.outGoingLinks[ptr] = new RefCountedSet(IterableWeakSet);
    }
    links.inc(ref);
    return this.tableManager.inc(ref);
  }
  deleteOutgoi
  // Add a link between an external object to an internal one.
  addIncomingLink(ref, ptr) {
    if (!this.incomingLinks.has(ref)) {
      this.incomingLinks[ref] = new RefCountedSet(Set);
    }
    this.incomingLinks[ref].inc(ptr);
  }
  // Start a cycle collection.
  // Internals
  //...
}
