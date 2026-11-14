#ifndef SETTINGS_MENU_H
#define SETTINGS_MENU_H

#include <Arduino.h>
#include <functional>
#include <vector>

// Forward declaration
class I2C;

// ---------------------------------------------------------------------------
// Estructuras de definición de menú
// ---------------------------------------------------------------------------

/** Tipo de acción que ejecuta un item de menú al presionar OK */
enum MenuAction {
    ACTION_NONE,              // Solo información, no hace nada
    ACTION_SUBMENU,           // Abrir submenú asociado
    ACTION_EXECUTE,           // Ejecutar callback directamente
    ACTION_CONFIRM_EXECUTE,   // Pedir confirmación antes de ejecutar
    ACTION_TOGGLE,            // Toggle valor booleano
    ACTION_VALUE_VIEW,        // Ver valor dinámico (texto generado)
};

/** Elemento individual de un menú */
struct MenuItem {
    const char* title;        // Línea 1 del LCD (máx 16 caracteres)
    const char* description;  // Línea 2 del LCD (scroll si es largo)
    MenuAction action;        // Qué hacer al presionar OK
    const void* submenu;      // Puntero a submenú (nullptr si no aplica)
    int menuId;               // ID del menú padre (para callbacks)
    int itemId;               // ID del item (para callbacks)
};

/** Menú = colección de items */
struct Menu {
    const char* name;         // Nombre interno del menú (para depuración)
    const MenuItem* items;    // Array de items
    int count;                // Número de items
};

// ---------------------------------------------------------------------------
// Callbacks
// ---------------------------------------------------------------------------

/** Callback ejecutado al seleccionar un item con ACTION_EXECUTE o ACTION_CONFIRM_EXECUTE */
typedef std::function<void(int menuId, int itemId)> MenuExecuteCallback;

/** Callback que devuelve el texto dinámico de un item (ACTION_VALUE_VIEW) */
typedef std::function<String(int menuId, int itemId)> MenuValueCallback;

/** Callback que devuelve el estado booleano actual (ACTION_TOGGLE) */
typedef std::function<bool(int menuId, int itemId)> MenuToggleGetCallback;

/** Callback que aplica el nuevo estado booleano (ACTION_TOGGLE) */
typedef std::function<void(int menuId, int itemId, bool value)> MenuToggleSetCallback;

// ---------------------------------------------------------------------------
// Clase principal
// ---------------------------------------------------------------------------

class SettingsMenu {
public:
    SettingsMenu();

    /** Inicializa el menú (no lo activa) */
    void begin();

    /** 
     * Actualiza el estado interno: animación, scroll, timeout, confirmación.
     * Llamar desde loop() frecuentemente.
     */
    void update();

    // ------------------------------------------------------------------
    // Activación
    // ------------------------------------------------------------------

    /**
     * Verifica si Power y Back están presionados simultáneamente.
     * Llamar cada ciclo cuando ambos botones estén activos.
     * Devuelve true si se detectó la combinación y comenzó la activación.
     */
    void checkActivation(bool powerPressed, bool backPressed);

    /** @return true si el menú está activo (mostrando opciones) */
    bool isActive() const;

    /** Cierra el menú y retorna al estado normal */
    void deactivate();

    // ------------------------------------------------------------------
    // Navegación
    // ------------------------------------------------------------------

    /** Mover a la opción anterior (cíclico) */
    void navigateLeft();

    /** Mover a la opción siguiente (cíclico) */
    void navigateRight();

    /** Presionar OK: entrar submenú o ejecutar acción */
    void select();

    /** Presionar BACK: volver al menú anterior o salir */
    void back();

    // ------------------------------------------------------------------
    // Display
    // ------------------------------------------------------------------

    /** Renderiza el menú actual en el LCD */
    void render(I2C& lcd);

    /** @return true si está reproduciendo la animación de entrada */
    bool isAnimating() const;

    // ------------------------------------------------------------------
    // Registro de menús
    // ------------------------------------------------------------------

    /** Establece el menú principal (raíz) */
    void setRootMenu(const Menu& menu);

    // ------------------------------------------------------------------
    // Registro de callbacks
    // ------------------------------------------------------------------

    /** Registra un callback de ejecución para un item */
    void onExecute(MenuExecuteCallback cb);

    /** Registra un callback de valor dinámico para un item */
    void onValue(MenuValueCallback cb);

    /** Registra callbacks de toggle para un item */
    void onToggle(MenuToggleGetCallback getCb, MenuToggleSetCallback setCb);

    // ------------------------------------------------------------------
    // Estado de consulta
    // ------------------------------------------------------------------

    /** @return índice del item actual en el menú actual */
    int getCurrentIndex() const;

    /** @return número total de items en el menú actual */
    int getCurrentCount() const;

    /** @return puntero al menú actual */
    const Menu* getCurrentMenu() const;

    /** @return profundidad actual del stack (0 = menú principal) */
    int getDepth() const;

private:
    // ------------------------------------------------------------------
    // Stack de navegación
    // ------------------------------------------------------------------

    struct StackFrame {
        const Menu* menu;
        int index;
    };

    static const int MAX_DEPTH = 4;
    std::vector<StackFrame> _stack;

    // ------------------------------------------------------------------
    // Animación de entrada
    // ------------------------------------------------------------------

    enum EntryState {
        ENTRY_IDLE,
        ENTRY_DETECTING,
        ENTRY_BLINKING,
        ENTRY_ACTIVE
    };

    EntryState _entryState = ENTRY_IDLE;
    unsigned long _comboStart = 0;
    unsigned long _blinkStart = 0;
    int _randomTextIndex = 0;

    static const unsigned long COMBO_HOLD_MS = 5000;
    static const unsigned long BLINK_DURATION_MS = 3000;
    static const unsigned long BLINK_INTERVAL_MS = 300;

    // ------------------------------------------------------------------
    // Timeout de inactividad
    // ------------------------------------------------------------------

    unsigned long _lastActivity = 0;
    static const unsigned long INACTIVITY_TIMEOUT_MS = 60000;

    // ------------------------------------------------------------------
    // Scroll de descripción
    // ------------------------------------------------------------------

    String _scrollText;
    int _scrollPos = 0;
    unsigned long _lastScroll = 0;
    static const unsigned long SCROLL_INTERVAL_MS = 300;
    static const int MENU_LCD_COLS = 16;

    // ------------------------------------------------------------------
    // Confirmación de acción peligrosa
    // ------------------------------------------------------------------

    bool _confirmActive = false;
    unsigned long _confirmStart = 0;
    int _confirmMenuId = -1;
    int _confirmItemId = -1;
    static const unsigned long CONFIRM_TIMEOUT_MS = 10000;

    // ------------------------------------------------------------------
    // Textos aleatorios para animación de parpadeo
    // ------------------------------------------------------------------

    static const char* RANDOM_TEXTS[];
    static const int RANDOM_TEXTS_COUNT;

    // ------------------------------------------------------------------
    // Callbacks registrados
    // ------------------------------------------------------------------

    MenuExecuteCallback _executeCb;
    MenuValueCallback _valueCb;
    MenuToggleGetCallback _toggleGetCb;
    MenuToggleSetCallback _toggleSetCb;

    // Menú raíz (se empuja al activar)
    const Menu* _rootMenu = nullptr;

    // ------------------------------------------------------------------
    // Métodos auxiliares
    // ------------------------------------------------------------------

    void pushMenu(const Menu& menu);
    void popMenu();
    void resetScroll();
    void updateScroll();
    void updateConfirmation();
    void executeAction(int menuId, int itemId);
    String getDisplayText(int menuId, int itemId) const;
    void padAndPrint(I2C& lcd, uint8_t line, const String& text);
};

#endif // SETTINGS_MENU_H
