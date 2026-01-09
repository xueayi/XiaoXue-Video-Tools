==================================================
[小雪工具箱] 视频压制任务开始
==================================================
[小雪工具箱] 执行命令:
D:\develop\galcriticism_video_tools\bin\ffmpeg.exe -y -i D:\develop\TGGA\main_final.mp4 -vf subtitles='D\\:/develop/TGGA/TGGA 完成稿v2.ass',scale=1920:1080 -c:v libx264 -crf 20 -preset medium -r 60 -c:a aac -b:a 192k D:\develop\TGGA\main_final2.mp4
--------------------------------------------------
ffmpeg version 8.0.1-full_build-www.gyan.dev Copyright (c) 2000-2025 the FFmpeg developers
  built with gcc 15.2.0 (Rev8, Built by MSYS2 project)
  configuration: --enable-gpl --enable-version3 --enable-static --disable-w32threads --disable-autodetect --enable-fontconfig --enable-iconv --enable-gnutls --enable-lcms2 --enable-libxml2 --enable-gmp --enable-bzlib --enable-lzma --enable-libsnappy --enable-zlib --enable-librist --enable-libsrt --enable-libssh --enable-libzmq --enable-avisynth --enable-libbluray --enable-libcaca --enable-libdvdnav --enable-libdvdread --enable-sdl2 --enable-libaribb24 --enable-libaribcaption --enable-libdav1d --enable-libdavs2 --enable-libopenjpeg --enable-libquirc --enable-libuavs3d --enable-libxevd --enable-libzvbi --enable-liboapv --enable-libqrencode --enable-librav1e --enable-libsvtav1 --enable-libvvenc --enable-libwebp --enable-libx264 --enable-libx265 --enable-libxavs2 --enable-libxeve --enable-libxvid --enable-libaom --enable-libjxl --enable-libvpx --enable-mediafoundation --enable-libass --enable-frei0r --enable-libfreetype --enable-libfribidi --enable-libharfbuzz --enable-liblensfun --enable-libvidstab --enable-libvmaf --enable-libzimg --enable-amf --enable-cuda-llvm --enable-cuvid --enable-dxva2 --enable-d3d11va --enable-d3d12va --enable-ffnvcodec --enable-libvpl --enable-nvdec --enable-nvenc --enable-vaapi --enable-libshaderc --enable-vulkan --enable-libplacebo --enable-opencl --enable-libcdio --enable-openal --enable-libgme --enable-libmodplug --enable-libopenmpt --enable-libopencore-amrwb --enable-libmp3lame --enable-libshine --enable-libtheora --enable-libtwolame --enable-libvo-amrwbenc --enable-libcodec2 --enable-libilbc --enable-libgsm --enable-liblc3 --enable-libopencore-amrnb --enable-libopus --enable-libspeex --enable-libvorbis --enable-ladspa --enable-libbs2b --enable-libflite --enable-libmysofa --enable-librubberband --enable-libsoxr --enable-chromaprint --enable-whisper
  libavutil      60.  8.100 / 60.  8.100
  libavcodec     62. 11.100 / 62. 11.100
  libavformat    62.  3.100 / 62.  3.100
  libavdevice    62.  1.100 / 62.  1.100
  libavfilter    11.  4.100 / 11.  4.100
  libswscale      9.  1.100 /  9.  1.100
  libswresample   6.  1.100 /  6.  1.100
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'D:\develop\TGGA\main_final.mp4':
  Metadata:
    major_brand     : isom
    minor_version   : 512
    compatible_brands: isomiso2avc1mp41
    encoder         : Lavf58.76.100
  Duration: 00:36:28.00, start: 0.000000, bitrate: 9147 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), 2160x1080, 8852 kb/s, 60 fps, 60 tbr, 15360 tbn (default)
    Metadata:
      handler_name    : VideoHandler
      vendor_id       : [0][0][0][0]
      timecode        : 00:00:00:00
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 256 kb/s (default)
    Metadata:
      handler_name    : SoundHandler
      vendor_id       : [0][0][0][0]
  Stream #0:2[0x3](eng): Data: none (tmcd / 0x64636D74)
    Metadata:
      handler_name    : TimeCodeHandler
      timecode        : 00:00:00:00
[Parsed_subtitles_0 @ 000001906d368e00] Unable to parse option value "/develop/TGGA/TGGA 完成稿v2.ass" as image size
[fc#-1 @ 000001906d368940] Error applying option 'original_size' to filter 'subtitles': Invalid argument
Error opening output file D:\develop\TGGA\main_final2.mp4.
Error opening output files: Invalid argument

[失败] FFmpeg 返回错误 (code=4294967274)



## 2
exe打包的软件压制时进入等待状态，控制台无任何日志输出，也没有实际执行