"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, X } from "lucide-react";

/**
 * Combobox компонент — select с возможностью поиска/фильтрации.
 * Используется вместо обычного <select> в модалях и фильтрах.
 * 
 * Props:
 *   value: string — текущее значение (id опции)
 *   onChange: (value: string) => void — колбек при выборе
 *   options: Array<{id, name}> — список опций
 *   placeholder: string — текст-подсказка (по умолчанию "Выберите...")
 *   disabled: bool — отключено ли
 *   required: bool — обязательно ли (для <select required>)
 */
export function Combobox({ value, onChange, options = [], placeholder = "Выберите...", disabled = false, required = false }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const inputRef = useRef(null);
  const containerRef = useRef(null);

  // Фильтруем опции по поисковому запросу (case-insensitive)
  const filtered = options.filter(
    (opt) =>
      opt.name.toLowerCase().includes(search.toLowerCase()) ||
      opt.id.toLowerCase().includes(search.toLowerCase())
  );

  // Находим выбранную опцию
  const selected = options.find((opt) => opt.id === value);

  // Закрываем на клик вне компонента
  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  // Фокус на input при открытии
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  function handleSelect(id) {
    onChange(id);
    setOpen(false);
    setSearch("");
  }

  function handleClear(e) {
    e.stopPropagation();
    onChange("");
    setSearch("");
  }

  return (
    <div className="fp-combobox-container" ref={containerRef}>
      <button
        type="button"
        className={`fp-combobox-trigger ${open ? "open" : ""} ${disabled ? "disabled" : ""}`}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
      >
        <span className="fp-combobox-value">
          {selected ? selected.name : <span className="fp-combobox-placeholder">{placeholder}</span>}
        </span>
        <span className="fp-combobox-icons">
          {value && !disabled && (
            <button type="button" className="fp-combobox-clear" onClick={handleClear}>
              <X size={14} />
            </button>
          )}
          <ChevronDown size={16} className={`fp-combobox-chevron ${open ? "rotated" : ""}`} />
        </span>
      </button>

      {open && (
        <div className="fp-combobox-popup">
          <input
            ref={inputRef}
            type="text"
            className="fp-combobox-search"
            placeholder="Поиск..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="fp-combobox-list">
            {filtered.length === 0 ? (
              <div className="fp-combobox-empty">Ничего не найдено</div>
            ) : (
              filtered.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className={`fp-combobox-option ${value === opt.id ? "selected" : ""}`}
                  onClick={() => handleSelect(opt.id)}
                >
                  {opt.name}
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* Скрытый select для валидации и доступности (может использоваться для required, name, etc.) */}
      <select
        style={{ display: "none" }}
        value={value}
        onChange={() => {}} // Управление через кнопку выше
        required={required}
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
    </div>
  );
}
