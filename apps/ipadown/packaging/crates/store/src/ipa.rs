//! IPA 文件元数据读取与去更新提示处理

use crate::error::Result;
use std::io::Read;
use std::path::Path;

/// 商店购买信息。位于 `Payload/*.app` 之外，不受代码签名保护。
const ITUNES_METADATA: &str = "iTunesMetadata.plist";

#[derive(Default)]
pub struct IpaMetadata {
    pub bundle_id: Option<String>,
    pub bundle_version: Option<String>,
    pub display_name: Option<String>,
}

pub fn read_metadata(ipa: &Path) -> Result<IpaMetadata> {
    let file = std::fs::File::open(ipa)?;
    let mut archive = zip::ZipArchive::new(file)?;
    for i in 0..archive.len() {
        let mut entry = match archive.by_index(i) {
            Ok(e) => e,
            Err(_) => continue,
        };
        let name = entry.name().to_string();
        if name.contains(".app/Info.plist") && !name.contains("/Watch/") {
            let mut buf = Vec::new();
            if entry.read_to_end(&mut buf).is_err() {
                continue;
            }
            if let Ok(plist::Value::Dictionary(d)) = plist::from_bytes::<plist::Value>(&buf) {
                let get = |k: &str| d.get(k).and_then(|v| v.as_string()).map(String::from);
                return Ok(IpaMetadata {
                    bundle_id: get("CFBundleIdentifier"),
                    bundle_version: get("CFBundleShortVersionString")
                        .or_else(|| get("CFBundleVersion")),
                    display_name: get("CFBundleDisplayName").or_else(|| get("CFBundleName")),
                });
            }
        }
    }
    Ok(IpaMetadata::default())
}

/// 删除 IPA 根目录的 iTunesMetadata.plist，安装后 App Store 不再提示更新。
/// 该文件不在签名的 .app 内，删除不影响原版签名；返回是否实际改写了文件。
/// 重写失败时返回错误并保留原 IPA，调用方继续使用即可。
pub fn strip_itunes_metadata(ipa: &Path) -> Result<bool> {
    let file = std::fs::File::open(ipa)?;
    let mut archive = zip::ZipArchive::new(file)?;
    if archive.by_name(ITUNES_METADATA).is_err() {
        return Ok(false);
    }
    // 序号区分并发的下载完成/安装请求，避免两个重写互相截断临时文件；
    // 同目录临时文件 + rename 原子替换。
    static STRIP_SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let seq = STRIP_SEQ.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let temp = ipa.with_extension(format!("{seq}.strip"));
    let outcome = rewrite_without_metadata(&mut archive, &temp)
        .and_then(|()| std::fs::rename(&temp, ipa).map_err(Into::into));
    if outcome.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    outcome.map(|()| true)
}

/// 逐条原样复制（不重新压缩），跳过 iTunesMetadata.plist。
fn rewrite_without_metadata(
    archive: &mut zip::ZipArchive<std::fs::File>,
    temp: &Path,
) -> Result<()> {
    let mut writer = zip::ZipWriter::new(std::fs::File::create(temp)?);
    for index in 0..archive.len() {
        let entry = archive.by_index_raw(index)?;
        if entry.name() == ITUNES_METADATA {
            continue;
        }
        writer.raw_copy_file(entry)?;
    }
    writer.finish()?.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn fixture(name: &str, with_metadata: bool) -> std::path::PathBuf {
        let path =
            std::env::temp_dir().join(format!("ipadown-ipa-{}-{name}.ipa", std::process::id()));
        let mut writer = zip::ZipWriter::new(std::fs::File::create(&path).unwrap());
        let options = zip::write::SimpleFileOptions::default();
        if with_metadata {
            writer.start_file(ITUNES_METADATA, options).unwrap();
            writer.write_all(b"<plist><dict/></plist>").unwrap();
        }
        writer
            .start_file("Payload/App.app/Info.plist", options)
            .unwrap();
        writer.write_all(b"signed payload").unwrap();
        writer.finish().unwrap();
        path
    }

    #[test]
    fn strip_removes_only_store_metadata() {
        let path = fixture("strip", true);
        assert!(strip_itunes_metadata(&path).unwrap());

        let mut archive = zip::ZipArchive::new(std::fs::File::open(&path).unwrap()).unwrap();
        assert!(archive.by_name(ITUNES_METADATA).is_err());
        let mut payload = String::new();
        archive
            .by_name("Payload/App.app/Info.plist")
            .unwrap()
            .read_to_string(&mut payload)
            .unwrap();
        assert_eq!(payload, "signed payload");

        // 已无该文件时幂等返回 false，不重写
        assert!(!strip_itunes_metadata(&path).unwrap());
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn strip_is_a_no_op_without_metadata() {
        let path = fixture("clean", false);
        assert!(!strip_itunes_metadata(&path).unwrap());
        std::fs::remove_file(&path).ok();
    }
}
