from ovn_bgp_vpnv4.allocator import DeterministicAllocator


def test_allocator_is_deterministic():
    allocator = DeterministicAllocator(rd_base=65000, rt_base=65000)
    first = allocator.allocate("tenant-a").as_tuple()
    second = allocator.allocate("tenant-a").as_tuple()

    assert first == second


def test_allocator_handles_collisions():
    allocator = DeterministicAllocator(rd_base=65000, rt_base=65000, max_id=16)

    a = allocator.allocate("tenant-a")
    b = allocator.allocate("tenant-b")

    assert a.as_tuple() != b.as_tuple()


def test_allocator_lookup():
    allocator = DeterministicAllocator(rd_base=64512, rt_base=64512)

    allocator.allocate("ns1")
    alloc = allocator.lookup("ns1")

    assert alloc is not None
    assert alloc.rd.startswith("64512:")

