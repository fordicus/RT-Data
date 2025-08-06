import asyncio, time
from dataclasses import dataclass
from typing import Optional
from util import my_name

@dataclass
class ConnectionState:
	"""연결 상태 관리"""
	task: asyncio.Task
	is_active: bool = False
	handoff_event: Optional[asyncio.Event] = None
	creation_time: float = 0.0

class HotSwapManager:
	
	def __init__(self):
		self.current_connection: Optional[ConnectionState] = None
		self.pending_connection: Optional[ConnectionState] = None
		self.swap_lock = asyncio.Lock()
		self.shutdown_event: Optional[asyncio.Event] = None
		self.hot_swap_tasks: list[asyncio.Task] = []

	def set_shutdown_event(self, shutdown_event: asyncio.Event):
		"""종료 이벤트 등록"""
		self.shutdown_event = shutdown_event
		
	def is_shutting_down(self) -> bool:
		"""종료 중인지 확인"""
		return self.shutdown_event and self.shutdown_event.is_set()

	async def graceful_shutdown(self, logger):
		"""Hot Swap 매니저 안전 종료"""
		async with self.swap_lock:
			logger.info(f"[{my_name()}] Shutting down HotSwapManager...")
			
			# 1. 먼저 새로운 Hot Swap 시작을 막기 위해 shutdown 상태 확인
			if not self.is_shutting_down():
				logger.warning(f"[{my_name()}] Shutdown event not set during graceful_shutdown")
			
			# 2. 대기 중인 백업 연결 정리 (우선순위 높음)
			if self.pending_connection:
				try:
					if not self.pending_connection.task.done():
						self.pending_connection.task.cancel()
						try:
							await asyncio.wait_for(
								self.pending_connection.task, 
								timeout=2.0
							)
						except (asyncio.CancelledError, asyncio.TimeoutError):
							pass
				except Exception as e:
					logger.warning(f"Failed to cleanup pending connection: {e}")
			
			# 3. 모든 Hot Swap 관련 태스크 정리 (schedule_backup_creation 포함)
			if self.hot_swap_tasks:
				logger.info(f"[{my_name()}] Cleaning up {len(self.hot_swap_tasks)} hot swap tasks...")
				
				# 모든 태스크를 먼저 cancel
				for i, task in enumerate(self.hot_swap_tasks):
					if not task.done():
						task.cancel()
						logger.debug(f"[{my_name()}] Cancelled hot swap task {i+1}")
				
				# 그 다음 완료를 기다림
				if self.hot_swap_tasks:
					try:
						# gather로 모든 태스크 대기
						results = await asyncio.wait_for(
							asyncio.gather(*self.hot_swap_tasks, return_exceptions=True),
							timeout=3.0
						)
						
						# 결과 분석
						cancelled_count = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
						error_count = sum(1 for r in results if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError))
						
						logger.info(
							f"[{my_name()}] Hot swap tasks cleanup complete: "
							f"{len(results)} total, {cancelled_count} cancelled, {error_count} errors"
						)
						
					except asyncio.TimeoutError:
						logger.warning(f"[{my_name()}] Some hot swap tasks cleanup timed out")
					except asyncio.CancelledError:
						logger.info(f"[{my_name()}] Hot swap tasks cleanup was cancelled")
					except Exception as e:
						logger.warning(f"[{my_name()}] Hot swap tasks cleanup error: {e}")
				
				self.hot_swap_tasks.clear()
			
			# 4. 상태 초기화
			self.current_connection = None
			self.pending_connection = None
			
			logger.info(f"[{my_name()}] HotSwapManager shutdown complete")

	def _cleanup_completed_tasks(self):
		"""완료된 태스크들을 정리하여 메모리 누수 방지"""
		self.hot_swap_tasks = [
			task for task in self.hot_swap_tasks 
			if not task.done()
		]

	async def initiate_hot_swap(self, task_factory, logger):
		"""Hot swap 시작 (종료 시에는 시작하지 않음)"""
		if self.is_shutting_down():
			logger.info(f"[{my_name()}] Hot swap cancelled - shutdown in progress")
			return

		async with self.swap_lock:
			if self.pending_connection:
				return
				
			logger.info(f"[{my_name()}] 🔌 New Conn Start")
			
			handoff_event = asyncio.Event()
			new_task = asyncio.create_task(
				task_factory(handoff_event, True)
			)
			
			# 태스크 추적에 추가 (완료된 태스크는 먼저 정리)
			self._cleanup_completed_tasks()
			self.hot_swap_tasks.append(new_task)
			
			self.pending_connection = ConnectionState(
				task=new_task,
				is_active=False,
				handoff_event=handoff_event,
				creation_time=time.time()
			)

	# pending_connection 상태 확인 메서드 추가
	def is_ready_for_handoff(self) -> bool:
		return (self.pending_connection is not None and 
				not self.pending_connection.task.done())

	async def _cleanup_old_connection(self, old_conn: ConnectionState, logger):
		"""기존 연결 안전하게 정리"""
		try:
			# 잠시 대기 후 정리 (데이터 중복 방지)
			await asyncio.sleep(1.0)
			
			if not old_conn.task.done():
				old_conn.task.cancel()
				try:
					await old_conn.task
				except asyncio.CancelledError:
					pass
					
			logger.info("[HotSwap] Old connection cleaned up")
			
		except Exception as e:
			logger.warning(f"[HotSwap] Cleanup error: {e}")
			
	async def complete_handoff(self, logger):
		"""연결 교체 완료"""
		async with self.swap_lock:
			if not self.pending_connection:
				return
				
			logger.info(f"[{my_name()}] 🤝 Handoff")
			
			# 2. 새 연결 활성화
			self.pending_connection.is_active = True
			self.pending_connection.handoff_event.set()
			
			# 3. 기존 연결 비활성화
			if self.current_connection:
				self.current_connection.is_active = False
				
			# 4. 연결 교체
			old_connection = self.current_connection
			self.current_connection = self.pending_connection
			self.pending_connection = None
			
			# 5. 기존 연결 정리 (별도 태스크로)
			if old_connection:
				asyncio.create_task(
					self._cleanup_old_connection(old_connection, logger)
				)

async def schedule_backup_creation(
	hot_swap_manager,
	backup_start_time: float,
	task_factory,
	logger,
	back_up_ready_ahead_sec: float,
	connection_start_time: float,
	check_interval: float = 1.0
):
	"""지정된 시간에 백업 생성을 스케줄링 (종료 인식)"""
	
	while True:
		# 종료 확인
		if hot_swap_manager.is_shutting_down():
			logger.info(f"[{my_name()}] Backup creation cancelled - shutdown in progress")
			return
			
		connection_age = time.time() - connection_start_time
		
		if connection_age >= backup_start_time:
			logger.info(
				f"[{my_name()}] 🔜 Backup Scheduled / "
				f"T-{back_up_ready_ahead_sec:.2f}s / "
				f"Age {connection_age:.2f}s"
			)
			
			await hot_swap_manager.initiate_hot_swap(task_factory, logger)
			break
			
		await asyncio.sleep(check_interval)