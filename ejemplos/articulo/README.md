# Configuraciones del artículo / Paper configurations

18 configuraciones de seis agentes: 14 base y cuatro con retirada/reincorporación de DG4. Las carpetas usan RDCF, COORDINATED_RCCRD y ROBUST_CONSENSUS como en el artículo. Importa `configuracion.json` desde el panel de configuración. Para ejecutarlas en placas, asigna tus dispositivos mediante el diálogo SSH/TCP.

They preserve the original mathematical inputs: 2000 indices, nominal minimum interval 0.001 s, demand 1150 kW, RDCF alpha=5e-11, RCCRD h=1e-6, consensus h=0.01. Withdrawal marks DG4 inactive for 750 <= k < 1250; its state is retained for re-entry. Endpoints are local and no real devices or credentials are included.

These are reproducible inputs, not raw records from the reported runs. The five startup presets remain separate in ../predeterminados and retain their previously saved parameters.
