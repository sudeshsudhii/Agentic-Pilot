import { Plug } from "lucide-react";
import { PluginManifest } from "../api/client";

type Props = {
  plugins: PluginManifest[];
};

export function PluginManager({ plugins }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Plugins</h2>
        <Plug size={18} />
      </div>
      <div className="plugin-list">
        {plugins.map((plugin) => (
          <article className="plugin-card" key={plugin.plugin_id}>
            <div>
              <h3>{plugin.name}</h3>
              <p>{plugin.sites.join(", ")}</p>
            </div>
            <div className="chip-row">
              {plugin.actions.map((action) => (
                <span className="chip" key={action}>
                  {action}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
