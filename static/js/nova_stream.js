class NovaStreamClient {
  constructor() {
    this.ws = null;
    this.sessionId = null;
  }

  connect() {
    if (this.ws) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/audio/nova`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.ws.send(
        JSON.stringify({
          type: "start",
          session_id: crypto.randomUUID(),
          sample_rate: 16000,
        }),
      );
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.session_id) {
        this.sessionId = msg.session_id;
      }
      console.log("Nova stream event", msg);
      if (msg.type === "reply" && msg.audio_url) {
        const audio = new Audio(msg.audio_url);
        audio.play().catch(() => {});
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.sessionId = null;
    };
  }

  sendDebugCommand(text) {
    if (!this.ws) return;
    this.ws.send(
      JSON.stringify({
        type: "debug_command",
        text,
        session_id: this.sessionId,
      }),
    );
  }

  stop() {
    if (!this.ws) return;
    this.ws.send(JSON.stringify({ type: "stop", session_id: this.sessionId }));
    this.ws.close();
  }
}

window.NovaStreamClient = NovaStreamClient;
