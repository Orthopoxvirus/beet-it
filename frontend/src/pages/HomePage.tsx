import { Link } from 'react-router-dom'
import { Library, Upload, Settings, Music } from 'lucide-react'

export default function HomePage() {
  return (
    <div className="space-y-8">
      <div className="text-center space-y-4">
        <img
          src="/beet-logo.svg"
          alt=""
          className="mx-auto h-24 w-24 md:h-40 md:w-40"
        />
        <h1 className="text-4xl font-bold">beet it</h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
          A modern web-based UI for managing your music libraries with beets.
          Import, organize, tag, and manage your entire music collection.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto">
        <Link
          to="/libraries"
          className="group p-6 border rounded-lg hover:border-primary hover:shadow-md transition-all"
        >
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="p-3 bg-primary/10 rounded-full group-hover:bg-primary/20 transition-colors">
              <Library className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Libraries</h2>
            <p className="text-muted-foreground">
              Manage multiple music libraries, view collections, and organize your music.
            </p>
          </div>
        </Link>

        <Link
          to="/import"
          className="group p-6 border rounded-lg hover:border-primary hover:shadow-md transition-all"
        >
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="p-3 bg-primary/10 rounded-full group-hover:bg-primary/20 transition-colors">
              <Upload className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Import</h2>
            <p className="text-muted-foreground">
              Import new music from folders or upload files directly through the web interface.
            </p>
          </div>
        </Link>

        <Link
          to="/settings"
          className="group p-6 border rounded-lg hover:border-primary hover:shadow-md transition-all"
        >
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="p-3 bg-primary/10 rounded-full group-hover:bg-primary/20 transition-colors">
              <Settings className="h-8 w-8 text-primary" />
            </div>
            <h2 className="text-xl font-semibold">Settings</h2>
            <p className="text-muted-foreground">
              Configure beets settings, manage plugins, and customize your workflow.
            </p>
          </div>
        </Link>
      </div>

      <div className="bg-muted/50 rounded-lg p-6 max-w-4xl mx-auto">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Music className="h-5 w-5" />
          Getting Started
        </h3>
        <ol className="list-decimal list-inside space-y-2 text-muted-foreground">
          <li>Create a new library to store your organized music collection</li>
          <li>Configure beets settings and plugins for your library</li>
          <li>Import music from your import folder or upload files directly</li>
          <li>Use the library browser to search, filter, and manage your collection</li>
        </ol>
      </div>
    </div>
  )
}
