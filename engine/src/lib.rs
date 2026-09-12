//! 小雪工具箱业务引擎 (Rust 移植版)。
//!
//! 与框架无关: Tauri/CLI 均可直接调用。每个模块对应 Python 版的一个
//! 业务模块, 单元测试与 Python 侧等价对齐。
//!
//! 注意: Shield (露骨图片识别) 不在移植范围, 由 Python 版承担。

pub mod batch;
pub mod ffmpeg;
pub mod folder;
pub mod notify;
pub mod paths;
pub mod probe;
pub mod version;
