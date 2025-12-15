import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  title = 'Sous Chef';
  url = '';
  loading = false;
  error: string | null = null;
  recipe: Recipe | null = null;
   // Normalized list of instruction steps for *ngFor
  steps: string[] = [];

  constructor(private recipeService: RecipeService) {}

  onScrape(): void {
    this.error = null;
    this.recipe = null;
    this.steps = [];

    const trimmedUrl = this.url.trim();
    if (!trimmedUrl) {
      this.error = 'Please enter a recipe URL';
      return;
    }

    this.loading = true;
    this.recipeService.scrape(trimmedUrl).subscribe({
      next: (data) => {
        this.recipe = data;
        const instructions = data.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.error = err?.error?.error || 'Failed to scrape recipe';
      },
    });
  }
}