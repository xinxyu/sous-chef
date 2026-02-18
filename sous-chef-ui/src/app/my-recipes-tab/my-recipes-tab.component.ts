import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Recipe } from '../recipe.service';

@Component({
  selector: 'app-my-recipes-tab',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './my-recipes-tab.component.html',
  styleUrls: ['./my-recipes-tab.component.scss'],
})
export class MyRecipesTabComponent {
  @Input() savedRecipes: Recipe[] = [];
  @Input() selectedRecipeIds: Set<string> = new Set<string>();

  @Output() loadRecipe = new EventEmitter<string>();
  @Output() deleteRecipe = new EventEmitter<string>();
  @Output() createMenu = new EventEmitter<void>();
  @Output() toggleSelection = new EventEmitter<string>();

  isSelected(recipeId: string): boolean {
    return this.selectedRecipeIds.has(recipeId);
  }

  onLoadRecipe(id: string): void {
    this.loadRecipe.emit(id);
  }

  onDeleteRecipe(id: string, event: Event): void {
    event.stopPropagation();
    this.deleteRecipe.emit(id);
  }

  onToggleSelection(recipeId: string, event?: Event): void {
    event?.stopPropagation();
    this.toggleSelection.emit(recipeId);
  }

  onCreateMenu(): void {
    this.createMenu.emit();
  }
}
