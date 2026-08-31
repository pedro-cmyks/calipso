use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use tauri::Manager;

pub struct ServerState(pub Arc<Mutex<Option<Child>>>);

fn calipso_root() -> std::path::PathBuf {
    if let Ok(root) = std::env::var("CALIPSO_ROOT") {
        return std::path::PathBuf::from(root);
    }
    dirs::home_dir()
        .unwrap_or_else(|| std::path::PathBuf::from("/home/pedro"))
        .join("calipso")
}

fn spawn_server(root: &std::path::Path) -> std::io::Result<Child> {
    let venv_uvicorn = root.join(".venv/bin/uvicorn");
    let uvicorn = if venv_uvicorn.exists() {
        venv_uvicorn
    } else {
        std::path::PathBuf::from("uvicorn")
    };
    Command::new(uvicorn)
        .args(["calipso.server:app", "--host", "127.0.0.1", "--port", "8000"])
        .current_dir(root)
        .spawn()
}

/// El token de esta instalacion, que el servidor genera en `~/.calipso/token`.
///
/// Es la credencial con la que el escritorio entra sin pedir TOTP. Antes aca
/// iba `CALIPSO_NO_TOTP=1`, que apagaba la autenticacion entera del servidor:
/// cualquier proceso de la maquina podia pedir `/login` con un codigo
/// cualquiera y llevarse la sesion, y el dia que esto salga por Tailscale
/// hubiera sido la autenticacion apagada para toda la tailnet.
fn calipso_token() -> Option<String> {
    let ruta = dirs::home_dir()?.join(".calipso").join("token");
    let tok = std::fs::read_to_string(ruta).ok()?;
    let tok = tok.trim().to_string();
    if tok.is_empty() { None } else { Some(tok) }
}

/// Espera hasta que el puerto 8000 acepte conexiones (máx. 30s).
fn wait_for_server() {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(30);
    while std::time::Instant::now() < deadline {
        if TcpStream::connect("127.0.0.1:8000").is_ok() {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(150));
    }
}

#[tauri::command]
fn server_url() -> String {
    "http://127.0.0.1:8000".to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = calipso_root();
    let child_handle: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let child_for_setup = child_handle.clone();
    let child_for_close = child_handle.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ServerState(child_handle))
        .setup(move |app| {
            match spawn_server(&root) {
                Ok(child) => {
                    *child_for_setup.lock().unwrap() = Some(child);
                    wait_for_server();
                }
                Err(e) => {
                    eprintln!("[calipso] No pude iniciar el servidor: {e}");
                }
            }

            // Permisos de WebKit: solo se concede lo que Calipso necesita de
            // verdad (microfono y camara, para la voz y la transcripcion). Todo
            // lo demas que WebKit pregunte —geolocalizacion, notificaciones,
            // enumerar dispositivos— se niega y se imprime, para que se vea que
            // algo lo pidio en vez de concederlo en silencio.
            //
            // Antes esto era `req.allow()` para cualquier permiso. El comentario
            // decia "microfono/camara" pero el codigo firmaba en blanco: con
            // `csp: null` en tauri.conf.json, una sola navegacion fuera de
            // 127.0.0.1 le entregaba camara y microfono a lo que cargara.
            #[cfg(target_os = "linux")]
            {
                use webkit2gtk::glib::Cast;
                use webkit2gtk::{PermissionRequestExt, UserMediaPermissionRequest,
                                 WebViewExt};
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.with_webview(|wv| {
                        wv.inner().connect_permission_request(|_, req| {
                            if req.downcast_ref::<UserMediaPermissionRequest>().is_some() {
                                req.allow();
                            } else {
                                eprintln!("[calipso] permiso de WebKit negado: {:?}",
                                          req.type_());
                                req.deny();
                            }
                            true
                        });
                    });
                }
            }

            // Entrar con el token en vez de saltear el TOTP. `auth_guard` del
            // servidor acepta `?token=...` y responde con la cookie de sesion,
            // asi que el escritorio no ve la pantalla de login y la
            // autenticacion sigue encendida para todo lo demas.
            if let Some(tok) = calipso_token() {
                if let Some(win) = app.get_webview_window("main") {
                    let destino = format!("http://127.0.0.1:8000/?token={tok}");
                    match tauri::Url::parse(&destino) {
                        Ok(url) => { let _ = win.navigate(url); }
                        Err(e) => eprintln!("[calipso] url invalida: {e}"),
                    }
                }
            } else {
                eprintln!("[calipso] sin ~/.calipso/token: va a pedir TOTP. \
                           Arranca el servidor una vez a mano para generarlo.");
            }

            Ok(())
        })
        .on_window_event(move |_window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(mut child) = child_for_close.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![server_url])
        .run(tauri::generate_context!())
        .expect("error al iniciar Calipso");
}
