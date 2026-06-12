"""FastAPI 应用入口。"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from app.config import AppConfig, load_config
from app.discord_monitor import DiscordMonitor
from app.forwarder import MessageForwarder
from app.models import LogEntry, LogLevel, Platform, SystemState
from app.persistence.llm_store import LlmConfigStore
from app.persistence.account_store import AccountStore
from app.persistence import close_mysql_pool
from app.persistence.prompt_store import PromptProfileStore
from app.persistence.store import LogStore
from app.persistence.trading_store import TradingStore
from app.routes import account, api, dashboard, signals, trading_controls, youtube
from app.services.dashboard.trading_controls import TradingControlsService
from app.services.signal_runtime import LiveSignalProcessor
from app.services.messages import MessageService
from app.services.wxpusher import WxPusherMonitor
from app.telegram_monitor import TelegramMonitor
from app.notifications import PositionWatcher
from app.services.wxpusher.shared import SharedWxPusherRuntime
from app.trading.execution import TradingExecutor
from app.websocket_manager import ws_manager

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kol-monitor")

system_state = SystemState()
config: AppConfig | None = None
message_service: MessageService | None = None
telegram_monitor: TelegramMonitor | None = None
discord_monitor: DiscordMonitor | None = None
wxpusher_monitor: WxPusherMonitor | None = None
forwarder: MessageForwarder | None = None
start_time = 0.0


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(1)
        system_state.uptime_seconds = int(time.time() - start_time)
        if message_service:
            await message_service.heartbeat()


async def _on_message(entry: LogEntry) -> None:
    if message_service:
        await message_service.submit(entry)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, message_service, telegram_monitor, discord_monitor
    global wxpusher_monitor, forwarder, start_time

    load_dotenv()
    config = load_config()
    store = LogStore(config.mysql)
    store.initialize()
    prompt_store = PromptProfileStore(config.mysql)
    prompt_store.initialize()
    llm_store = LlmConfigStore(config.mysql)
    llm_store.initialize()
    trading_store = TradingStore(config.mysql)
    trading_store.initialize()
    account_store = AccountStore(config.mysql)
    account_store.initialize()
    shared_wxpusher = SharedWxPusherRuntime(config)
    shared_wxpusher.initialize()
    message_service = MessageService(system_state, store, ws_manager)
    await message_service.load_recent()
    trading_executor = TradingExecutor(config, trading_store)
    signal_processor = LiveSignalProcessor(config, trading_executor)
    trading_controls_service = TradingControlsService(config)

    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.config = config
    app.state.system_state = system_state
    app.state.ws_manager = ws_manager
    app.state.log_store = store
    app.state.prompt_store = prompt_store
    app.state.llm_store = llm_store
    app.state.trading_store = trading_store
    app.state.account_store = account_store
    app.state.shared_wxpusher = shared_wxpusher
    app.state.trading_executor = trading_executor
    app.state.trading_controls_service = trading_controls_service
    app.state.message_service = message_service

    forwarder = MessageForwarder(config)
    telegram_monitor = TelegramMonitor(config, system_state.telegram)
    discord_monitor = DiscordMonitor(config, system_state.discord)
    wxpusher_monitor = WxPusherMonitor(config, system_state.wxpusher, shared_wxpusher)
    app.state.discord_monitor = discord_monitor
    app.state.wxpusher_monitor = wxpusher_monitor
    forwarder.set_telegram(telegram_monitor)
    forwarder.set_discord(discord_monitor)
    message_service.set_forwarder(forwarder)
    message_service.set_signal_processor(signal_processor)
    position_watcher = PositionWatcher(config)

    start_time = time.time()
    await message_service.submit(
        LogEntry.create(
            level=LogLevel.INFO,
            platform=Platform.SYSTEM,
            content="系统启动，正在连接 Telegram、Discord 和 WxPusher",
        ),
        allow_forward=False,
    )
    await telegram_monitor.start(on_message=_on_message)
    await discord_monitor.start(on_message=_on_message)
    await wxpusher_monitor.start(on_message=_on_message)
    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    position_task = asyncio.create_task(position_watcher.run())
    logger.info("server ready at http://%s:%s", config.host, config.port)

    yield

    heartbeat_task.cancel()
    position_task.cancel()
    await telegram_monitor.stop()
    await discord_monitor.stop()
    await wxpusher_monitor.stop()
    close_mysql_pool()


app = FastAPI(
    title="KOL Monitor Trade",
    description="实时接入 Telegram、Discord 和 WxPusher 消息，并提供仪表盘查看日志和连接状态。",
    version="1.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(dashboard.router)
app.include_router(api.router)
app.include_router(signals.router)
app.include_router(account.router)
app.include_router(trading_controls.router)


app.include_router(youtube.router)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "heartbeat",
            "data": system_state.to_dict(ws_clients=ws_manager.active_count),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)
