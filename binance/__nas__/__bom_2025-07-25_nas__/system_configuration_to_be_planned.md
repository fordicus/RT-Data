---

🛠 OS 및 소프트웨어 스택

계층	기술	설명

OS	Ubuntu 22.04 LTS	최신 커널 + RDMA + ZFS 패키지 안정 지원
파일시스템	ZFS (zfsutils-linux)	단일 SSD ZFS 풀 구성<br>압축(lz4/zstd), ARC 활성화<br>L2ARC, SLOG 미사용
네트워크	iSER (iSCSI Extensions for RDMA)	targetcli-fb + open-iscsi + rdma-core 사용<br>Mellanox mlx5 드라이버로 RDMA 직결
드라이버	mlx5_core, nvme, zfs, iscsi_trgt	모두 kernel module 또는 DKMS 설치 가능
통신 구성	GX‑10 ↔ NAS 간 직결 (SFP28 DAC)	스위치 불필요, 지연 최소화 설정 가능

---