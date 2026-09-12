//! 小雪工具箱业务引擎 (Rust 移植版)。
//!
//! 与框架无关: Tauri/CLI 均可直接调用。每个模块对应 Python 版的一个
//! 业务模块, 单元测试与 Python 侧等价对齐。

pub mod ffmpeg;
pub mod version;
