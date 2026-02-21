import { bootstrapApplication } from '@angular/platform-browser';
import { provideHttpClient } from '@angular/common/http';
import { AppComponent } from './app/app.component';
import { environment } from './environments/environment';

// In dev, use current host for API so mobile (e.g. http://192.168.1.5:4200) calls the same machine on :4100
if (!environment.production && typeof window !== 'undefined') {
  (environment as { apiUrl: string }).apiUrl = `${window.location.protocol}//${window.location.hostname}:4100`;
}

bootstrapApplication(AppComponent, {
  providers: [provideHttpClient()],
}).catch((err) => console.error(err));
