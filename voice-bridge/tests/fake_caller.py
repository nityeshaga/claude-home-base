#!/usr/bin/env python3
"""Pretend to be the browser: stream spoken sentences into the bridge, print what comes back.

usage: venv/bin/python tests/fake_caller.py "Hi, what did we talk about today?" ["second sentence" ...]
Each sentence is synthesised with macOS `say`, converted to PCM16 mono 24 kHz, streamed in
100 ms chunks, then we wait for the reply before sending the next one. Output audio is
discarded; transcripts and statuses are printed. Set WAIT=<sec> to change the per-sentence wait.
"""
import asyncio, json, os, ssl, subprocess, sys, tempfile, time
import websockets

URL = os.environ.get("BRIDGE", "wss://localhost:9443/ws")  # add ?user=<slack id> to pick the caller; default is the first entry in callers.json
WAIT = float(os.environ.get("WAIT", "45"))


def synth(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        aiff, wav = f"{d}/s.aiff", f"{d}/s.wav"
        subprocess.run(["say", "-v", "Samantha", "-o", aiff, text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", aiff, wav], check=True)
        return open(wav, "rb").read()[44:]  # strip WAV header


async def main(sentences):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    audio_bytes = 0
    async with websockets.connect(URL, ssl=ctx, max_size=None) as ws:
        async def reader():
            nonlocal audio_bytes
            async for m in ws:
                if isinstance(m, bytes):
                    audio_bytes += len(m); continue
                ev = json.loads(m)
                if ev.get("type") == "transcript":
                    if not ev.get("partial"):
                        print(f"  [{ev['role']}] {ev['text']}")
                    else:
                        print(f"\r  [{ev['role']}~] {ev['text'][:110]}", end="", flush=True)
                        if ev['text'].rstrip().endswith(('.', '?', '!')): print()
                else:
                    print(f"  <{ev.get('type')}> {ev.get('text') or ev.get('seconds')}")
        rt = asyncio.create_task(reader())
        await asyncio.sleep(2)
        for s in sentences:
            print(f"\n>>> saying: {s}")
            pcm = synth(s)
            for i in range(0, len(pcm), 4800):
                await ws.send(pcm[i:i+4800]); await asyncio.sleep(0.1)
            # keep sending silence so the model can take its turn
            t0 = time.time()
            while time.time() - t0 < WAIT:
                await ws.send(b"\x00" * 4800); await asyncio.sleep(0.1)
        await ws.send(json.dumps({"type": "hangup"}))
        await asyncio.sleep(2)
        rt.cancel()
    print(f"\naudio received: {audio_bytes/48000:.1f}s")

asyncio.run(main(sys.argv[1:] or ["Hi, can you hear me?"]))
