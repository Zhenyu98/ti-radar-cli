function rstd_dofile(varargin)
% rstd_dofile(luaPath1, luaPath2, ...)
% 连接 mmWave Studio 的 RSTD 自动化服务(127.0.0.1:2777)，依次 dofile 各 lua 脚本。
% 复用 DCA_Connet/Init_RSTD_Connection 的思路，但自包含（不依赖参考项目文件）。
% 成功打印 RSTD_DOFILE_OK，供 Python 侧判定。

    dllPath = ['C:\ti\mmwave_studio_02_01_01_00\mmWaveStudio\Clients\' ...
               'RtttNetClientController\RtttNetClientAPI.dll'];

    if strcmp(which('RtttNetClientAPI.RtttNetClient.IsConnected'), '')
        asm = NET.addAssembly(dllPath);
        if ~strcmp(asm.Classes{1}, 'RtttNetClientAPI.RtttClient')
            error('RSTD assembly 加载异常，检查 DLL 路径: %s', dllPath);
        end
    end

    connected = false;
    try
        connected = RtttNetClientAPI.RtttNetClient.IsConnected();
    catch
        connected = false;
    end

    if ~connected
        es = RtttNetClientAPI.RtttNetClient.Init();
        if es ~= 0, error('RSTD Init 失败: %d', es); end
        es = RtttNetClientAPI.RtttNetClient.Connect('127.0.0.1', 2777);
        if es ~= 0
            error(['RSTD Connect 失败: %d。在 mmWaveStudio Lua 控制台执行 ' ...
                   'RSTD.NetClose() 再 RSTD.NetStart() 后重试'], es);
        end
        pause(1);
    end

    for i = 1:numel(varargin)
        luaPath = varargin{i};
        luaCmd = sprintf('dofile("%s")', strrep(luaPath, '\', '\\'));
        fprintf('>> %s\n', luaCmd);
        status = RtttNetClientAPI.RtttNetClient.SendCommand(luaCmd);
        fprintf('RSTD status=%d  (%s)\n', status, luaPath);
        if status ~= 30000
            error('RSTD SendCommand 失败(%d): %s', status, luaPath);
        end
    end

    fprintf('RSTD_DOFILE_OK\n');
end
