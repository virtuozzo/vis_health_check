from .framework import BaseCheck, CheckResult
from utils import vstorage_file_stats, run_cmd


class StorageClusterStatusCheck(BaseCheck):
    name = "storage_cluster_status"

    def __init__(self, vinfra, overview, ctx=None):
        super().__init__(ctx)
        self.overview = overview
        self.vinfra = vinfra

    def run(self):
        self.logger.info("Checking storage cluster status")

        details = []

        try:
            number_of_cses = self.vinfra.run(
                "cluster",
                "settings",
                "number-of-cses-per-disk",
                "show",
            )

            for tier, value in number_of_cses.items():
                if tier.startswith("tier") and value > 1:
                    details.append(
                        f"{tier}: {value} chunk servers per disk configured"
                    )

            cses_config = self.vinfra.run("cses-config", "show")
            if cses_config.get("rdma"):
                details.append("RDMA is enabled")

        except Exception as exc:
            return CheckResult(
                self.name,
                "ERROR",
                [f"Failed to collect storage cluster settings: {exc}"],
            )

        cluster_status = self.overview.get("status")

        if cluster_status != "healthy":
            details.append(f"Cluster status: {cluster_status}")
            return CheckResult(self.name, "FAIL", details)

        return CheckResult(self.name, "OK", details)

class TierFreeSpaceCheck(BaseCheck):
    name = "tier_free_space"
    WARN_THRESHOLD = 15.0
    FAIL_THRESHOLD = 5.0

    def __init__(self, overview, ctx=None):
        super().__init__(ctx)
        self.overview = overview

    def run(self):
        self.logger.info("Checking storage tiers free space")

        tiers = self.overview["tiers"]
        if not isinstance(tiers, list):
            tiers = [tiers]

        stats, warn, fail = [], [], []

        for tier in tiers:
            total = float(tier["phys_space"]["total"])
            free = float(tier["phys_space"]["free"])
            percent = (free / total) * 100
            stats.append({"tier": tier["id"], "free": f"{percent:.2f}%"})

            if percent <= self.FAIL_THRESHOLD:
                fail.append(f"{tier['id']} {percent:.2f}%")
            elif percent <= self.WARN_THRESHOLD:
                warn.append(f"{tier['id']} {percent:.2f}%")

        if fail:
            return CheckResult(self.name, "FAIL", fail)
        if warn:
            return CheckResult(self.name, "WARN", warn)

        return CheckResult(self.name, "OK", stats)


class MDSHealthCheck(BaseCheck):
    name = "mds_health"

    CPU_THRESHOLD = 80.0
    CTIME_THRESHOLD = 80.0


    def __init__(self, vstorage_stat, overview, ctx=None):
        super().__init__(ctx)
        self.vstorage_stat = vstorage_stat
        self.overview = overview

    def run(self):
        self.logger.info("Checking MDS")

        problems = []

        # Quantity check
        mds = self.overview["mds"]
        if mds["failed"] > 0:
            problems.append(f"Failed MDS count: {mds['failed']}")

        if mds["total"] != 5:
            problems.append(f"MDS total is {mds['total']} (expected 5)")

        # CPU check
        for m in self.vstorage_stat["mds_list"]["mds"]:
            cpu_avg5 = float(m["cpu_usage"]["avg5m"])
            ctime_avg5 = float(m["ctime"]["avg5m"])
            if m["status"] != "avail" or cpu_avg5 > self.CPU_THRESHOLD or ctime_avg5 > self.CTIME_THRESHOLD:
                problems.append(
                        f"MDS {m['id']} status={m['status']} cpu_avg5m={cpu_avg5} ctime_avg5m={ctime_avg5} "
                    )

        if problems:
            return CheckResult(self.name, "WARN", problems)

        return CheckResult(self.name, "OK")



class ChunkServerErrorCheck(BaseCheck):
    name = "chunk_server_errors"

    def __init__(self, vstorage_stat, ctx=None):
        super().__init__(ctx)
        self.vstorage_stat = vstorage_stat

    def run(self):
        self.logger.info("Checking CSes")

        try:
            cses = self.vstorage_stat["cs_list"]["cs"]

            errors = []

            for cs in cses:
                if cs["last_err"] != "0" or cs["last_link_err"] != "0":
                    errors.append(
                        f"CS {cs['id']} last_err={cs['last_err']} "
                        f"link_err={cs['last_link_err']}"
                    )

            if errors:
                return CheckResult(self.name, "FAIL", errors)

            return CheckResult(self.name, "OK")

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])

class IOQueueDepthCheck(BaseCheck):
    name = "io_queue_depth"

    QDEPTH_THRESHOLD = 10.0

    def __init__(self, vstorage_stat, ctx=None):
        super().__init__(ctx)
        self.vstorage_stat = vstorage_stat

    def run(self):
        self.logger.info("Checking IO QDepths")

        try:
            high = []

            cs_list = self.vstorage_stat["cs_list"]["cs"]

            for cs in cs_list:
                avg5 = float(cs["io_stat"]["ioqueue"]["avg5m"])
                if avg5 >= self.QDEPTH_THRESHOLD:
                    high.append(f"CS {cs['id']} avg5m={avg5}")

            cluster_avg = float(self.vstorage_stat["io_stat"]["queue_aver"])
            if cluster_avg >= self.QDEPTH_THRESHOLD:
                high.append(f"Cluster queue_aver={cluster_avg}")

            if high:
                return CheckResult(self.name, "WARN", high)

            return CheckResult(self.name, "OK")

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])

class ReplicaOneFilesCheck(BaseCheck):
    name = "replica_one_files"

    def __init__(self, cluster_name, ctx=None):
        super().__init__(ctx)
        self.cluster_name = cluster_name

    def run(self):
        self.logger.info("Checking unique checks")

        try:
            stats = vstorage_file_stats(self.cluster_name)

            for entry in stats:
                if entry["stor-type"] == "1r":
                    count = int(entry["files"])
                    if count > 0:
                        return CheckResult(
                            self.name,
                            "WARN",
                            [f"Files with Replica=1: {count}"]
                        )

            return CheckResult(self.name, "OK")

        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])


class DisksHealthCheck(BaseCheck):
    name = "disk_health"

    def __init__(self,hosts, ctx=None):
        super().__init__(ctx)
        self.hosts = hosts

    def run(self):
        self.logger.info("Checking disks health")
        acceptable_states = {'true', 'n/a'}

        problems = []
        try:
            disk_monitor = run_cmd(["vstorage-disks-monitor", "health", "--monitor.address",
                                    "backend-api.svc.vstoragedomain:9988"])
            disks_info = [line for line in disk_monitor.split('\n')]
            for disk in disks_info[1:]:
                disk_health = disk.split()
                if disk_health[-1] not in acceptable_states:
                   problems.append(f"Host: {disk_health[2]}, Disk: {disk_health[3]} is not in healthy status")
                if disk_health[1] != 'active':
                    problems.append(f"Host: {disk_health[2]}, Disk: {disk_health[3]} is in {disk_health[1]} status")

            if problems:
                return CheckResult(self.name, "FAIL", problems)

            return CheckResult(self.name, "OK")
        except Exception as e:
            return CheckResult(self.name, "ERROR", [str(e)])


