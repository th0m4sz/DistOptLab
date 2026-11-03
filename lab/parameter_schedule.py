# Función de este módulo: Valida y consulta cambios de una referencia común por índice local.
"""No modifica estados ni añade una ley de control o una corrección de balance."""
import copy


class ParameterSchedule:
    def __init__(self, config, fields):
        self.base = copy.deepcopy(config['parameters'])
        self.key, self.events = None, []
        schedule = config.get('demand_schedule')
        if schedule is None:
            return
        if not isinstance(schedule, dict) or schedule.get('version') != 1:
            raise ValueError('Formato de cambios de demanda no soportado')
        key = schedule.get('parameter')
        field = next((f for f in fields if f.key == key), None)
        if field is None or getattr(field, 'type', None) not in ('number', 'integer'):
            raise ValueError('La demanda debe corresponder a un parámetro común numérico declarado')
        events = schedule.get('events')
        if not isinstance(events, list) or not 1 <= len(events) <= 30:
            raise ValueError('Programa entre 1 y 30 cambios de demanda')
        used = set()
        for event in events:
            if not isinstance(event, dict):
                raise ValueError('Cambio de demanda inválido')
            at = event.get('at')
            if type(at) is not int or not 1 <= at < config['steps'] or at in used:
                raise ValueError('Cada cambio necesita un índice único entre 1 y la penúltima actualización')
            value = field.validate(event.get('value'))
            used.add(at)
            self.events.append((at, value))
        self.events.sort()
        self.key = key

    def at(self, k):
        """El valor nuevo se utiliza desde la actualización k → k+1."""
        values = dict(self.base)
        if self.key is not None:
            for at, value in self.events:
                if k < at:
                    break
                values[self.key] = value
        return values

    def across(self, indices):
        """Un reloj reconstruido puede contener referencias locales diferentes."""
        values = dict(self.base)
        if self.key is not None:
            references = {self.at(k)[self.key] for k in indices}
            values[self.key] = next(iter(references)) if len(references) == 1 else None
        return values


def reference_values(rt, k=None, indices=None):
    schedule = getattr(rt, 'parameter_schedule', None)
    if schedule is None or schedule.key is None:
        return {}
    values = schedule.across(indices) if indices is not None else schedule.at(0 if k is None else k)
    return {'reference/' + schedule.key: values[schedule.key]}
