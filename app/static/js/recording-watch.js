(function () {
    const cfg = window.RECORDING_WATCH || {};
    const video = document.getElementById('rec-video');
    const stage = document.getElementById('rec-stage');
    const loading = document.getElementById('rec-loading');
    const errorEl = document.getElementById('rec-error');
    const playBtn = document.getElementById('rec-play');
    const fsBtn = document.getElementById('rec-fullscreen');
    const progress = document.getElementById('rec-progress');
    const curTime = document.getElementById('rec-cur-time');
    const durTime = document.getElementById('rec-dur-time');
    const volBtn = document.getElementById('rec-mute');
    const volRange = document.getElementById('rec-volume');
    const speedBtn = document.getElementById('rec-speed');
    const centerPlay = document.getElementById('rec-center-play');

    let hls = null;
    let hideTimer = null;
    const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
    let speedIdx = speeds.indexOf(1);

    function fmt(sec) {
        if (!isFinite(sec) || sec < 0) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return m + ':' + String(s).padStart(2, '0');
    }

    function showError(msg) {
        loading.classList.add('hidden');
        errorEl.textContent = msg;
        errorEl.classList.remove('hidden');
    }

    function setPlayingUI(playing) {
        stage.classList.toggle('paused', !playing);
        playBtn.innerHTML = playing
            ? '<i class="fas fa-pause"></i>'
            : '<i class="fas fa-play"></i>';
    }

    function updateProgress() {
        if (!video.duration) return;
        progress.value = (video.currentTime / video.duration) * 1000;
        curTime.textContent = fmt(video.currentTime);
        durTime.textContent = fmt(video.duration);
    }

    function togglePlay() {
        if (video.paused) {
            video.play().catch(function () {});
        } else {
            video.pause();
        }
    }

    function toggleFullscreen() {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else if (stage.requestFullscreen) {
            stage.requestFullscreen();
        }
    }

    function resetHideTimer() {
        stage.classList.remove('hide-ui');
        clearTimeout(hideTimer);
        if (!video.paused) {
            hideTimer = setTimeout(function () {
                stage.classList.add('hide-ui');
            }, 3000);
        }
    }

    function initPlayer() {
        const url = cfg.playbackUrl;
        const isHls = cfg.isHls;

        if (!url) {
            showError('No playback URL.');
            return;
        }

        if (isHls && window.Hls && Hls.isSupported()) {
            hls = new Hls({ enableWorker: true });
            hls.loadSource(url);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, function () {
                loading.classList.add('hidden');
                video.play().catch(function () {
                    stage.classList.add('paused');
                });
            });
            hls.on(Hls.Events.ERROR, function (e, data) {
                if (data.fatal) {
                    showError('Playback failed. Close this tab and open Watch again.');
                }
            });
        } else if (isHls && video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = url;
            video.addEventListener('loadedmetadata', function () {
                loading.classList.add('hidden');
                video.play().catch(function () { stage.classList.add('paused'); });
            });
        } else {
            showError('HLS player not supported. Hard refresh and try again.');
            return;
        }

        video.addEventListener('play', function () { setPlayingUI(true); resetHideTimer(); });
        video.addEventListener('pause', function () {
            setPlayingUI(false);
            stage.classList.remove('hide-ui');
            clearTimeout(hideTimer);
        });
        video.addEventListener('timeupdate', updateProgress);
        video.addEventListener('loadedmetadata', updateProgress);
        video.addEventListener('click', togglePlay);

        playBtn.addEventListener('click', function (e) { e.stopPropagation(); togglePlay(); });
        centerPlay.addEventListener('click', function (e) { e.stopPropagation(); togglePlay(); });
        fsBtn.addEventListener('click', function (e) { e.stopPropagation(); toggleFullscreen(); });

        progress.addEventListener('input', function () {
            if (video.duration) {
                video.currentTime = (progress.value / 1000) * video.duration;
            }
        });

        volRange.addEventListener('input', function () {
            video.volume = volRange.value / 100;
            video.muted = false;
            volBtn.innerHTML = video.volume === 0
                ? '<i class="fas fa-volume-mute"></i>'
                : '<i class="fas fa-volume-up"></i>';
        });

        volBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            video.muted = !video.muted;
            volBtn.innerHTML = video.muted
                ? '<i class="fas fa-volume-mute"></i>'
                : '<i class="fas fa-volume-up"></i>';
        });

        speedBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            speedIdx = (speedIdx + 1) % speeds.length;
            video.playbackRate = speeds[speedIdx];
            speedBtn.textContent = speeds[speedIdx] + 'x';
        });

        stage.addEventListener('mousemove', resetHideTimer);
        stage.addEventListener('touchstart', resetHideTimer);

        document.addEventListener('keydown', function (e) {
            if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
            if (e.code === 'KeyF') toggleFullscreen();
            if (e.code === 'ArrowRight') video.currentTime += 5;
            if (e.code === 'ArrowLeft') video.currentTime -= 5;
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPlayer);
    } else {
        initPlayer();
    }
})();
